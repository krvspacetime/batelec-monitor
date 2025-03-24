import json


def cache_to_file(data: dict, filename: str) -> None:
    try:
        with open(filename, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        raise Exception(f"Failed to cache data: {e}")


def get_cached_data(filename: str | None = None) -> dict:
    try:
        if filename is None:
            with open("cache/cached_data.json", "r") as f:
                return json.load(f)
        else:
            with open(filename, "r") as f:
                return json.load(f)
    except Exception as e:
        raise Exception(f"Failed to get cached data: {e}")
