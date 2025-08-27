# Python Networking Lab  ![CI](https://github.com/Mamat078/python-networking-lab/actions/workflows/ci.yml/badge.svg)


[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)](https://github.com/pre-commit/pre-commit)

Exercise repository for learning Python applied to networking:

-SSH automation (Netmiko)

-Multi-vendor data collection (NAPALM)

-Orchestration (Nornir + Jinja2)

-Validation (pyATS/Genie)

-Source of Truth (NetBox API)

_Repo testé sur [Cisco DevNet Sandbox](https://developer.cisco.com/site/sandbox/) – IOS XE on Cat8kv._
## Cisco DevNet Sandbox Connection

Pour accéder au lab, connexion via **OpenConnect** :

```bash
# Exemple de connexion au sandbox IOS XE on Cat8kv
sudo openconnect FQDN:port \
    --user=username
--> password
