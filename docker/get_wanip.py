import json

from network_probe import collect_network_status


if __name__ == "__main__":
    status = collect_network_status()
    print(json.dumps(status.to_dict(), ensure_ascii=False, indent=2))
