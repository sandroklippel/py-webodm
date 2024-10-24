import json
from urllib.parse import urlunparse


def fmt_endpoint(scheme, netloc, path):
    return urlunparse((scheme, netloc, path, "", "", ""))


def save_preset(name, options):
    with open("{}.preset".format(name), "w") as savefile:
        json.dump(options, savefile)


def read_preset(fn):
    with open(fn, "r") as jsonfile:
        try:
            preset = json.load(jsonfile)
        except json.JSONDecodeError:
            preset = {"auto-boundary": True}
    return preset


def odmpreset_to_dict(l):
    return {i["name"]: i["value"] for i in l}


def fmt_time_span(td):
    if td.days > 0:
        return f"{td.days}d {td.seconds // 3600}h {td.seconds % 3600 // 60}m {td.seconds % 60}s"
    elif td.seconds >= 3600:
        return f"{td.seconds // 3600}h {td.seconds % 3600 // 60}m {td.seconds % 60}s"
    elif td.seconds >= 60:
        return f"{td.seconds // 60}m {td.seconds % 60}s"
    else:
        return f"{td.seconds}s {td.microseconds // 1000}ms"


def fmt_size(value):
    sizeunits = ["B", "KB", "MB", "GB", "TB"]
    i = 2
    while value >= 1024 and i < len(sizeunits) - 1:
        value /= 1024
        i += 1
    return f"{value:.2f} {sizeunits[i]}"
