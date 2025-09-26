# Python Networking Lab  ![CI](https://github.com/Mamat078/python-networking-lab/actions/workflows/ci.yml/badge.svg) [![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)](https://github.com/pre-commit/pre-commit)
# Network Automation Lab

This repository is my personal learning lab for **Python applied to Network Automation**.  
The objective is to move beyond manual CLI work and explore how Python can streamline day-to-day network operations while providing hands-on practice with tools used in real environments.  

Tested primarily on **Cisco DevNet Sandbox** (IOS XE on Cat8kv).  

---

## 🔧 Tools & Libraries

- **[Netmiko](https://github.com/ktbyers/netmiko)** → SSH automation to network devices  
- **[NAPALM](https://napalm.readthedocs.io/)** → Multi-vendor abstraction for retrieving facts, configs, and diffs  
- **[Black](https://black.readthedocs.io/)** → Code formatter for consistent Python style  
- **[Ruff](https://docs.astral.sh/ruff/)** → Linter and static analysis for clean, optimized code  

---

## 📂 Repository Structure

- **`/source/ssh/`** → Contains Python scripts built during the learning phase:  
  - **Command execution** → Automates common *show* commands on Cisco devices  
  - **Configuration backup** → Retrieves and stores running configuration  

> ⚠️ NAPALM testing is included, but command execution is limited due to **sandbox environment incompatibility** and restrictions.  

---

## 📈 Current Progress

✅ Netmiko scripts for command execution  
✅ Automated configuration backups  
✅ CI/CD integration with Black + Ruff for clean code  
⚠️ Limited NAPALM execution on Cisco Sandbox  

---

## 🧪 Why this project?

This repository is an **exercise environment** to learn Python for networking:  

1. **SSH automation** with Netmiko  
2. **Multi-vendor data collection** with NAPALM  
3. **Code quality & CI/CD** with Black + Ruff  

It is meant as a stepping stone to:  
- Automate repetitive network tasks  
- Standardize configuration management  
- Build habits aligned with professional workflows  

---

## 🚀 Next Stage

- The **infrastructure lab (CCNP-level topology)** used for advanced testing will be documented in a separate repo: **`infra-ccnp`**.  
- The continuation of this project with **Ansible** for market-standard orchestration will be detailed in another dedicated repo: **`automatisation-ansible`**.  

This way, each part of the journey (Python basics, infra setup, Ansible orchestration) is modular and easy to follow.  

---

## 🖥️ Lab Environment

Using Cisco DevNet Sandbox:  

```bash
# Example connection with OpenConnect
sudo openconnect FQDN:port \
    --user=username
# → Enter password when prompted
