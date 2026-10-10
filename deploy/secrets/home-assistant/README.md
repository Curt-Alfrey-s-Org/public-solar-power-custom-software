# Home Assistant long-lived token

Store your Home Assistant long-lived access token on the **operator machine only**.

Do not commit token files to git. Mount or copy the token at deploy time on the host that runs
Home Assistant or MQTT discovery tools.
