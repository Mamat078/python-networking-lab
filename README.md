# Python Networking Lab  ![CI](https://github.com/Mamat078/python-networking-lab/actions/workflows/ci.yml/badge.svg)

[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)](https://github.com/pre-commit/pre-commit)

_Network Automation Lab_

This repository is my personal learning lab for network automation. The project is written in Python and currently makes use of:

Netmiko → for establishing SSH sessions to network devices and executing commands.

NAPALM → for abstracted multi-vendor management (retrieving facts, pushing configs, comparing diffs).

The goal of this repo is to progressively build a solid foundation in automation as part of my journey toward the CCNP certification.

Current Progress

Built Python scripts to connect to Cisco devices using Netmiko.

Automated execution of show commands and backups.

Started experimenting with NAPALM for configuration management and state retrieval.

Next Steps

Explore Ansible for playbook-based orchestration.

Learn Terraform for infrastructure-as-code approaches to networking.

Integrate tests and best practices for repeatable automation workflows.

Why this project?

I want to move beyond manual CLI work and learn how to:

Automate repetitive network operations.

Standardize configuration management.

Gain hands-on practice with the same tools used in professional environments.

---

_Exercise repository for learning Python applied to networking:_

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
