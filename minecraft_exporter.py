#!/usr/bin/python
import sys
sys.path.insert(0, "lib/NBT")
sys.path.insert(0, "lib/mcrcon")

from prometheus_client import start_http_server, REGISTRY, Metric
import time
import requests
import json
import nbt
import re
# import pprint
import argparse
from mcrcon import MCRcon
from os import listdir
from os.path import isfile, join
class MinecraftCollector(object):
    def __init__(self):
        self.parse_commandline()
        self.directoryes = {
            'stats': self.args.world + '/stats',
            'playerdata': self.args.world + '/playerdata',
            'advancements': self.args.world + '/advancements',
        }
        self.users_cache = dict()
        self.rcon = None

    def parse_commandline(self):
        parser = argparse.ArgumentParser(description='Minecraft prometheus exporter')
        parser.add_argument("-w", "--world", help="World path", required=True)
        parser.add_argument("-H", "--rcon-host", help="RCON host", default='localhost')
        parser.add_argument("-P", "--rcon-port", help="RCON port", default=25575)
        parser.add_argument("-p", "--rcon-password", help="RCON password", required=True)
        parser.add_argument("-e", "--exporter-port", help="Exporter port to listen", default=9010)

        self.args = parser.parse_args()
        print(self.args)

    def get_players(self):
        return [f[:-5] for f in listdir(self.directoryes['stats']) if isfile(join(self.directoryes['stats'], f))]

    def flush_playernamecache(self):
        print("flushing playername cache")
        self.users_cache = dict()
        return

    def uuid_to_player(self,uuid):
        uuid = uuid.replace('-','')
        if uuid in self.users_cache:
            return self.users_cache[uuid]
        else:
            try:
                result = requests.get('https://api.mojang.com/user/profiles/' + uuid + '/names')
                self.users_cache[uuid] = result.json()[-1]['name']
                return(result.json()[-1]['name'])
            except:
                return

    def rcon_command(self,command):
        if self.rcon == None:
            self.rcon = MCRcon(self.args.rcon_host,self.args.rcon_password,self.args.rcon_port)
            self.rcon.connect()
        try:
            response = self.rcon.command(command)
        except BrokenPipeError:
            print("Lost RCON Connection, trying to reconnect")
            self.rcon.connect()
            response = self.rcon.command(command)

        return response

    def get_server_stats(self):
        metrics = []
        player_online    = Metric('minecraft_player_online',"is 1 if player is online","counter")

        metrics.extend([player_online])

        # player
        resp = self.rcon_command("list")
        playerregex = re.compile("players online:(.*)")
        if playerregex.findall(resp):
            for player in playerregex.findall(resp)[0].split(","):
                if not player.isspace():
                    player_online.add_sample('minecraft_player_online',value=1,labels={'player':player.lstrip()})

        return metrics

    def get_player_stats(self,uuid):
        with open(self.directoryes['stats']+"/"+uuid+".json") as json_file:
            data = json.load(json_file)
            json_file.close()
        data['stats']['minecraft:external'] = {}
        nbtfile = nbt.nbt.NBTFile(self.directoryes['playerdata']+"/"+uuid+".dat",'rb')
        data['stats']['minecraft:custom']["nbt:xptotal"]    = nbtfile.get("XpTotal").value
        data['stats']['minecraft:custom']["nbt:xplevel"]    = nbtfile.get("XpLevel").value
        data['stats']['minecraft:custom']["nbt:score"]      = nbtfile.get("Score").value
        data['stats']['minecraft:custom']["nbt:health"]     = nbtfile.get("Health").value
        data['stats']['minecraft:custom']["nbt:foodlevel"]  = nbtfile.get("foodLevel").value
        data['stats']['minecraft:external']["nbt:dimension"]= nbtfile.get("Dimension").value.split(':')[1]
        # pprint.pprint(nbtfile.get("Inventory").value)
        with open(self.directoryes['advancements']+"/"+uuid+".json") as json_file:
            count = 0
            advancements = json.load(json_file)
            for key, value in advancements.items():
                if key in ("DataVersion"):
                  continue
                if value["done"] == True:
                    count += 1
        data['stats']['minecraft:custom']["advancements:advancements_done"] = count
        # pprint.pprint(data)
        return data

    def extract_name(self, value):
        return value.split(':')[1]

    def update_metrics_for_player(self,uuid):
        name = self.uuid_to_player(uuid)
        if not name: return
        data = self.get_player_stats(uuid)
        metrics = {
            'broken'   : { 'metric': Metric('minecraft_player_broken','Broken items by player',"counter")        , 'value_tag_name': 'item' },
            'crafted'  : { 'metric': Metric('minecraft_player_crafted','Crafted items by player',"counter")      , 'value_tag_name': 'item' },
            'dropped'  : { 'metric': Metric('minecraft_player_dropped','Dropped items by player',"counter")      , 'value_tag_name': 'item' },
            'mined'    : { 'metric': Metric('minecraft_player_mined','Broken items by player',"counter")         , 'value_tag_name': 'item' },
            'used'     : { 'metric': Metric('minecraft_player_used','Used items by player',"counter")            , 'value_tag_name': 'item' },
            'picked_up': { 'metric': Metric('minecraft_player_picked_up','Picked up items by player',"counter")  , 'value_tag_name': 'item' },
            'custom'   : { 'metric': Metric('minecraft_player_custom','Some stats from player',"counter")        , 'value_tag_name': 'metric' },
            'killed'   : { 'metric': Metric('minecraft_player_killed','Entityes, killed by player',"counter")    , 'value_tag_name': 'entity' },
            'killed_by': { 'metric': Metric('minecraft_player_killed_by','Entityes, who killed player',"counter"), 'value_tag_name': 'entity' },
        }
        for group_key, group_value in data['stats'].items():
            group_name = self.extract_name(group_key)
            for metric_key, metric_value in group_value.items():
                metric_name = self.extract_name(metric_key)
                if group_name in metrics:
                    metrics[group_name]['metric'].add_sample('minecraft_player_{}'.format(group_name),value=metric_value,labels={'player':name,metrics[group_name]['value_tag_name']:metric_name})
        player_dimension = Metric('minecraft_player_dimension','Current player dimension',"gauge")
        player_dimension.add_sample('minecraft_player_dimension',value=1,labels={'player':name, 'dimension':data['stats']['minecraft:external']["nbt:dimension"]})
        return [
            metrics['broken']['metric'],
            metrics['crafted']['metric'],
            metrics['dropped']['metric'],
            metrics['mined']['metric'],
            metrics['used']['metric'],
            metrics['picked_up']['metric'],
            metrics['custom']['metric'],
            metrics['killed']['metric'],
            metrics['killed_by']['metric'],
            player_dimension
            ]

    def collect(self):
        for player in self.get_players():
            metrics = self.update_metrics_for_player(player)
            if not metrics: continue

            for metric in metrics:
                yield metric

        for metric in self.get_server_stats():
            yield metric

if __name__ == '__main__':
    collector = MinecraftCollector()
    start_http_server(int(collector.args.exporter_port))
    REGISTRY.register(collector)
    print("Exporter started on Port {}".format(int(collector.args.exporter_port)))
    while True:
        time.sleep(1)
