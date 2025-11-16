import urllib.request
import urllib.error
import json
import time
import datetime
import random
import argparse

URL_SUMMARY = "https://status.openai.com/api/v2/summary.json"
VERBOSE = False

def ts():
    return datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

def parse_max_age(headers, default_seconds):
    cc = headers.get("Cache-Control") or headers.get("cache-control") or ""
    parts = [p.strip() for p in cc.split(",") if p]
    for p in parts:
        if p.startswith("max-age="):
            try:
                return max(5, int(p.split("=", 1)[1]))
            except Exception:
                pass
    return default_seconds

def request_summary(etag, last_modified):
    headers = {"User-Agent": "StatusWatcher/1.0"}
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified
    req = urllib.request.Request(URL_SUMMARY, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            status = resp.getcode()
            body = resp.read()
            hdrs = dict(resp.info().items())
            return status, body, hdrs, None
    except urllib.error.HTTPError as e:
        hdrs = dict(e.headers.items()) if e.headers else {}
        return e.code, b"", hdrs, e
    except Exception as e:
        return None, b"", {}, e

def vprint(msg):
    if VERBOSE:
        print(msg)

def status_phrase(s):
    if not s:
        return "Unknown"
    return s.replace("_", " ").strip().capitalize()

def latest_update_text_for_component(incidents, comp_id, comp_name):
    best = None
    best_time = None
    for inc in incidents or []:
        affects = False
        comps = inc.get("components")
        if isinstance(comps, list):
            for c in comps:
                if isinstance(c, dict):
                    if c.get("id") == comp_id or c.get("name") == comp_name:
                        affects = True
                        break
                elif isinstance(c, str):
                    if c == comp_id or c == comp_name:
                        affects = True
                        break
        if not affects:
            ids = inc.get("component_ids") or inc.get("affected_components")
            if isinstance(ids, list):
                for c in ids:
                    if isinstance(c, dict):
                        if c.get("id") == comp_id or c.get("name") == comp_name:
                            affects = True
                            break
                    elif isinstance(c, str):
                        if c == comp_id:
                            affects = True
                            break
        if not affects:
            continue
        updates = inc.get("incident_updates") or []
        for u in updates:
            t = u.get("created_at") or u.get("updated_at") or ""
            try:
                dt = datetime.datetime.fromisoformat(t.replace("Z", "+00:00"))
            except Exception:
                dt = datetime.datetime.min
            if best_time is None or dt > best_time:
                best_time = dt
                best = u.get("body") or u.get("status")
    return best

def component_names_for_incident(incident, components_by_id):
    names = []
    comps = incident.get("components")
    if isinstance(comps, list):
        for c in comps:
            if isinstance(c, dict):
                n = c.get("name")
                if n:
                    names.append(n)
    ids = incident.get("component_ids") or incident.get("affected_components")
    if isinstance(ids, list):
        for c in ids:
            if isinstance(c, dict):
                i = c.get("id")
                if i and i in components_by_id:
                    names.append(components_by_id[i]["name"])
                else:
                    n = c.get("name")
                    if n:
                        names.append(n)
            elif isinstance(c, str):
                if c in components_by_id:
                    names.append(components_by_id[c]["name"])
    return list(dict.fromkeys(names))

def run_once(seed_seen, components_prev):
    etag = None
    last_modified = None
    max_age = 60
    status, body, hdrs, err = request_summary(etag, last_modified)
    if status == 200:
        etag = hdrs.get("ETag") or hdrs.get("etag")
        last_modified = hdrs.get("Last-Modified") or hdrs.get("last-modified")
        max_age = parse_max_age(hdrs, 60)
        data = json.loads(body.decode("utf-8"))
        components = data.get("components") or []
        incidents = data.get("incidents") or []
        components_by_id = {c.get("id"): c for c in components}
        if seed_seen:
            pass
        else:
            for inc in incidents:
                updates = inc.get("incident_updates") or []
                for u in updates:
                    uid = u.get("id") or ""
                    SEEN.add(uid)
        for c in components:
            cid = c.get("id")
            name = c.get("name") or "Unknown"
            curr = c.get("status")
            prev = components_prev.get(cid)
            if prev is not None and prev != curr:
                if curr != "operational":
                    msg = latest_update_text_for_component(incidents, cid, name)
                    print(f"[{ts()}] Product: {name}")
                    if msg:
                        print(f"Status: {msg}")
                    else:
                        print(f"Status: {status_phrase(curr)}")
            components_prev[cid] = curr
        for inc in incidents:
            updates = inc.get("incident_updates") or []
            latest = None
            latest_id = None
            latest_time = None
            for u in updates:
                t = u.get("created_at") or u.get("updated_at") or ""
                try:
                    dt = datetime.datetime.fromisoformat(t.replace("Z", "+00:00"))
                except Exception:
                    dt = datetime.datetime.min
                if latest_time is None or dt > latest_time:
                    latest_time = dt
                    latest = u
                    latest_id = u.get("id") or ""
            if latest_id and latest_id not in SEEN:
                names = component_names_for_incident(inc, components_by_id)
                msg = latest.get("body") or latest.get("status") or inc.get("name")
                if names:
                    for n in names:
                        print(f"[{ts()}] Product: {n}")
                        print(f"Status: {msg}")
                else:
                    print(f"[{ts()}] Product: OpenAI API")
                    print(f"Status: {msg}")
                SEEN.add(latest_id)
        return max_age
    return max_age

def run_loop(bootstrap_log=False):
    etag = None
    last_modified = None
    components_prev = {}
    max_age = 60
    seeded = False
    while True:
        status, body, hdrs, err = request_summary(etag, last_modified)
        if status == 304:
            sleep_s = int(max(5, parse_max_age(hdrs, max_age)))
            sleep_s = int(sleep_s * random.uniform(0.9, 1.1))
            vprint(f"[{ts()}] No change, next check in ~{sleep_s}s")
            time.sleep(sleep_s)
            continue
        if status == 200:
            etag = hdrs.get("ETag") or hdrs.get("etag")
            last_modified = hdrs.get("Last-Modified") or hdrs.get("last-modified")
            max_age = parse_max_age(hdrs, max_age)
            data = json.loads(body.decode("utf-8"))
            components = data.get("components") or []
            incidents = data.get("incidents") or []
            components_by_id = {c.get("id"): c for c in components}
            if not seeded:
                for inc in incidents:
                    updates = inc.get("incident_updates") or []
                    for u in updates:
                        uid = u.get("id") or ""
                        SEEN.add(uid)
                if bootstrap_log:
                    for c in components:
                        name = c.get("name") or "Unknown"
                        curr = c.get("status")
                        if curr and curr != "operational":
                            msg = latest_update_text_for_component(incidents, c.get("id"), name)
                            print(f"[{ts()}] Product: {name}")
                            if msg:
                                print(f"Status: {msg}")
                            else:
                                print(f"Status: {status_phrase(curr)}")
                seeded = True
            for c in components:
                cid = c.get("id")
                name = c.get("name") or "Unknown"
                curr = c.get("status")
                prev = components_prev.get(cid)
                if prev is not None and prev != curr:
                    if curr != "operational":
                        msg = latest_update_text_for_component(incidents, cid, name)
                        print(f"[{ts()}] Product: {name}")
                        if msg:
                            print(f"Status: {msg}")
                        else:
                            print(f"Status: {status_phrase(curr)}")
                components_prev[cid] = curr
            for inc in incidents:
                updates = inc.get("incident_updates") or []
                latest = None
                latest_id = None
                latest_time = None
                for u in updates:
                    t = u.get("created_at") or u.get("updated_at") or ""
                    try:
                        dt = datetime.datetime.fromisoformat(t.replace("Z", "+00:00"))
                    except Exception:
                        dt = datetime.datetime.min
                    if latest_time is None or dt > latest_time:
                        latest_time = dt
                        latest = u
                        latest_id = u.get("id") or ""
                if latest_id and latest_id not in SEEN:
                    names = component_names_for_incident(inc, components_by_id)
                    msg = latest.get("body") or latest.get("status") or inc.get("name")
                    if names:
                        for n in names:
                            print(f"[{ts()}] Product: {n}")
                            print(f"Status: {msg}")
                    else:
                        print(f"[{ts()}] Product: OpenAI API")
                        print(f"Status: {msg}")
                    SEEN.add(latest_id)
            bad = [c for c in components if (c.get("status") or "operational") != "operational"]
            if VERBOSE:
                if bad:
                    names = ", ".join([c.get("name") or "Unknown" for c in bad])
                    vprint(f"[{ts()}] Non-operational components: {names}")
                else:
                    vprint(f"[{ts()}] All components operational")
            sleep_s = int(max(5, max_age))
            sleep_s = int(sleep_s * random.uniform(0.9, 1.1))
            time.sleep(sleep_s)
            continue
        retry = 30
        ra = hdrs.get("Retry-After") or hdrs.get("retry-after")
        if ra:
            try:
                retry = max(5, int(ra))
            except Exception:
                pass
        time.sleep(int(retry * random.uniform(0.9, 1.1)))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--bootstrap-log", action="store_true")
    parser.add_argument("--url", type=str, default="https://status.openai.com/api/v2/summary.json")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    global SEEN
    SEEN = set()
    global URL_SUMMARY
    URL_SUMMARY = args.url
    global VERBOSE
    VERBOSE = args.verbose
    if args.once:
        components_prev = {}
        max_age = run_once(args.bootstrap_log, components_prev)
        print(f"Next check in ~{max(5, int(max_age))}s")
        return
    run_loop(bootstrap_log=args.bootstrap_log)

if __name__ == "__main__":
    main()