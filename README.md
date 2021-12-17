# minecraft-exporter

this is a prometheus minecraft exporter
This exporter reads minecrafts nbt files, the advancements files and can optionally connect via RCON to your minecraft server.

rcon connection is used to get online Players

to enable rcon on your minecraft server add the following to the server.properties file:

```
broadcast-rcon-to-ops=false
rcon.port=25575
rcon.password=Password
enable-rcon=true
```

# Usage

```
minecraft_exporter.py -w /path/to/world -p rcon_pw
```
