#!/bin/bash
# Heimdallr Configuration Manager
# Manage monitored services and settings
#
# Requirements: Python 3 with PyYAML (pip install pyyaml)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
CONFIG_FILE="${HEIMDALLR_CONFIG:-$PROJECT_DIR/config.yaml}"
CONFIG_EXAMPLE="$PROJECT_DIR/config.example.yaml"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# ─────────────────────────────────────────────────────────────────────────────
# Helper Functions
# ─────────────────────────────────────────────────────────────────────────────

check_config() {
    if [[ ! -f "$CONFIG_FILE" ]]; then
        echo -e "${YELLOW}Config file not found: $CONFIG_FILE${NC}"
        echo ""
        if [[ -f "$CONFIG_EXAMPLE" ]]; then
            read -p "Create from config.example.yaml? [Y/n] " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]] || [[ -z $REPLY ]]; then
                cp "$CONFIG_EXAMPLE" "$CONFIG_FILE"
                echo -e "${GREEN}Created $CONFIG_FILE${NC}"
            else
                exit 1
            fi
        else
            echo -e "${RED}No config.example.yaml found either${NC}"
            exit 1
        fi
    fi
}

# Python helper for YAML operations
run_python() {
    python3 - "$@" << 'PYTHON_SCRIPT'
import sys
import yaml
from pathlib import Path

def load_config(path):
    with open(path) as f:
        return yaml.safe_load(f)

def save_config(path, config):
    with open(path, 'w') as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

def cmd_list(config_path):
    config = load_config(config_path)
    mon = config.get('monitoring', {})

    print("\n\033[1;36m═══════════════════════════════════════════\033[0m")
    print("\033[1;36m  Heimdallr - Configured Services\033[0m")
    print("\033[1;36m═══════════════════════════════════════════\033[0m\n")

    # Amplify Apps
    apps = mon.get('amplify_apps', [])
    print(f"\033[1;34mAmplify Apps ({len(apps)}):\033[0m")
    if apps:
        for app in apps:
            app_id = app.get('app_id', 'unknown')
            name = app.get('name', 'unnamed')
            log_group = app.get('log_group', f'/aws/amplify/{app_id}')
            print(f"  • {name}")
            print(f"    ID: {app_id}")
            print(f"    Logs: {log_group}")
    else:
        print("  (none configured)")
    print()

    # EC2 Instances
    instances = mon.get('ec2_instances', [])
    print(f"\033[1;34mEC2 Instances ({len(instances)}):\033[0m")
    if instances:
        for inst in instances:
            inst_id = inst.get('instance_id', 'unknown')
            name = inst.get('name', 'unnamed')
            services = inst.get('services', [])
            print(f"  • {name}")
            print(f"    ID: {inst_id}")
            if services:
                print(f"    Services: {', '.join(services)}")
    else:
        print("  (none configured)")
    print()

    # Intervals
    print("\033[1;34mPolling Intervals:\033[0m")
    print(f"  • Log polling:    {mon.get('log_poll_interval', 30)}s")
    print(f"  • Health checks:  {mon.get('health_check_interval', 60)}s")
    print(f"  • Error lookback: {mon.get('error_lookback_minutes', 5)} min")
    print()

def cmd_add_amplify(config_path, app_id, name):
    config = load_config(config_path)
    if 'monitoring' not in config:
        config['monitoring'] = {}
    if 'amplify_apps' not in config['monitoring']:
        config['monitoring']['amplify_apps'] = []

    # Check if already exists
    for app in config['monitoring']['amplify_apps']:
        if app.get('app_id') == app_id:
            print(f"\033[1;33mAmplify app {app_id} already configured\033[0m")
            return

    config['monitoring']['amplify_apps'].append({
        'app_id': app_id,
        'name': name
    })
    save_config(config_path, config)
    print(f"\033[1;32mAdded Amplify app: {name} ({app_id})\033[0m")

def cmd_add_ec2(config_path, instance_id, name, services=None):
    config = load_config(config_path)
    if 'monitoring' not in config:
        config['monitoring'] = {}
    if 'ec2_instances' not in config['monitoring']:
        config['monitoring']['ec2_instances'] = []

    # Check if already exists
    for inst in config['monitoring']['ec2_instances']:
        if inst.get('instance_id') == instance_id:
            print(f"\033[1;33mEC2 instance {instance_id} already configured\033[0m")
            return

    entry = {
        'instance_id': instance_id,
        'name': name
    }
    if services:
        entry['services'] = services.split(',')

    config['monitoring']['ec2_instances'].append(entry)
    save_config(config_path, config)
    print(f"\033[1;32mAdded EC2 instance: {name} ({instance_id})\033[0m")

def cmd_remove(config_path, service_type, service_id):
    config = load_config(config_path)
    mon = config.get('monitoring', {})

    if service_type == 'amplify':
        apps = mon.get('amplify_apps', [])
        original_len = len(apps)
        mon['amplify_apps'] = [a for a in apps if a.get('app_id') != service_id]
        if len(mon['amplify_apps']) < original_len:
            save_config(config_path, config)
            print(f"\033[1;32mRemoved Amplify app: {service_id}\033[0m")
        else:
            print(f"\033[1;33mAmplify app not found: {service_id}\033[0m")

    elif service_type == 'ec2':
        instances = mon.get('ec2_instances', [])
        original_len = len(instances)
        mon['ec2_instances'] = [i for i in instances if i.get('instance_id') != service_id]
        if len(mon['ec2_instances']) < original_len:
            save_config(config_path, config)
            print(f"\033[1;32mRemoved EC2 instance: {service_id}\033[0m")
        else:
            print(f"\033[1;33mEC2 instance not found: {service_id}\033[0m")
    else:
        print(f"\033[1;31mUnknown service type: {service_type}\033[0m")
        print("Use 'amplify' or 'ec2'")

def cmd_interval(config_path, interval_type, value):
    config = load_config(config_path)
    if 'monitoring' not in config:
        config['monitoring'] = {}

    try:
        value = int(value)
    except ValueError:
        print(f"\033[1;31mInvalid value: {value} (must be integer)\033[0m")
        return

    key_map = {
        'log': 'log_poll_interval',
        'logs': 'log_poll_interval',
        'poll': 'log_poll_interval',
        'health': 'health_check_interval',
        'check': 'health_check_interval',
        'lookback': 'error_lookback_minutes',
        'error': 'error_lookback_minutes'
    }

    key = key_map.get(interval_type)
    if not key:
        print(f"\033[1;31mUnknown interval type: {interval_type}\033[0m")
        print("Use: log, health, or lookback")
        return

    old_value = config['monitoring'].get(key, 'not set')
    config['monitoring'][key] = value
    save_config(config_path, config)

    unit = 'min' if 'minutes' in key else 's'
    print(f"\033[1;32mSet {key}: {old_value} → {value}{unit}\033[0m")

def cmd_show(config_path):
    config = load_config(config_path)
    print(yaml.dump(config, default_flow_style=False, sort_keys=False))

# Main
if __name__ == '__main__':
    args = sys.argv[1:]
    if len(args) < 2:
        print("Usage: Called from shell script")
        sys.exit(1)

    cmd = args[0]
    config_path = args[1]

    if cmd == 'list':
        cmd_list(config_path)
    elif cmd == 'add-amplify' and len(args) >= 4:
        cmd_add_amplify(config_path, args[2], args[3])
    elif cmd == 'add-ec2' and len(args) >= 4:
        services = args[4] if len(args) > 4 else None
        cmd_add_ec2(config_path, args[2], args[3], services)
    elif cmd == 'remove' and len(args) >= 4:
        cmd_remove(config_path, args[2], args[3])
    elif cmd == 'interval' and len(args) >= 4:
        cmd_interval(config_path, args[2], args[3])
    elif cmd == 'show':
        cmd_show(config_path)
    else:
        print(f"Unknown command or missing args: {cmd}")
        sys.exit(1)
PYTHON_SCRIPT
}

# ─────────────────────────────────────────────────────────────────────────────
# Commands
# ─────────────────────────────────────────────────────────────────────────────

usage() {
    echo -e "${CYAN}Heimdallr Configuration Manager${NC}"
    echo ""
    echo "Usage: $0 COMMAND [options]"
    echo ""
    echo -e "${YELLOW}Commands:${NC}"
    echo "  list                           List all configured services and intervals"
    echo "  show                           Show full config.yaml contents"
    echo ""
    echo -e "${YELLOW}Add Services:${NC}"
    echo "  add amplify <app_id> <name>    Add an Amplify app to monitor"
    echo "  add ec2 <instance_id> <name> [services]"
    echo "                                 Add an EC2 instance (services: comma-separated)"
    echo ""
    echo -e "${YELLOW}Remove Services:${NC}"
    echo "  remove amplify <app_id>        Remove an Amplify app"
    echo "  remove ec2 <instance_id>       Remove an EC2 instance"
    echo ""
    echo -e "${YELLOW}Set Intervals:${NC}"
    echo "  interval log <seconds>         Set log polling interval (default: 30)"
    echo "  interval health <seconds>      Set health check interval (default: 60)"
    echo "  interval lookback <minutes>    Set error lookback window (default: 5)"
    echo ""
    echo -e "${YELLOW}Examples:${NC}"
    echo "  $0 list"
    echo "  $0 add amplify d18ed2fn05chf8 ChameleonLabs"
    echo "  $0 add ec2 i-0abc123 WebServer nginx,node"
    echo "  $0 interval health 300"
    echo "  $0 remove amplify d18ed2fn05chf8"
    echo ""
    echo -e "${YELLOW}Environment:${NC}"
    echo "  HEIMDALLR_CONFIG    Path to config.yaml (default: ../config.yaml)"
    echo ""
}

# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

if [[ $# -eq 0 ]]; then
    usage
    exit 0
fi

case $1 in
    list)
        check_config
        run_python list "$CONFIG_FILE"
        ;;
    show)
        check_config
        run_python show "$CONFIG_FILE"
        ;;
    add)
        check_config
        if [[ $# -lt 4 ]]; then
            echo -e "${RED}Usage: $0 add <amplify|ec2> <id> <name> [services]${NC}"
            exit 1
        fi
        case $2 in
            amplify)
                run_python add-amplify "$CONFIG_FILE" "$3" "$4"
                ;;
            ec2)
                run_python add-ec2 "$CONFIG_FILE" "$3" "$4" "${5:-}"
                ;;
            *)
                echo -e "${RED}Unknown service type: $2${NC}"
                echo "Use 'amplify' or 'ec2'"
                exit 1
                ;;
        esac
        ;;
    remove|rm)
        check_config
        if [[ $# -lt 3 ]]; then
            echo -e "${RED}Usage: $0 remove <amplify|ec2> <id>${NC}"
            exit 1
        fi
        run_python remove "$CONFIG_FILE" "$2" "$3"
        ;;
    interval|int)
        check_config
        if [[ $# -lt 3 ]]; then
            echo -e "${RED}Usage: $0 interval <log|health|lookback> <value>${NC}"
            exit 1
        fi
        run_python interval "$CONFIG_FILE" "$2" "$3"
        ;;
    help|-h|--help)
        usage
        ;;
    *)
        echo -e "${RED}Unknown command: $1${NC}"
        usage
        exit 1
        ;;
esac
