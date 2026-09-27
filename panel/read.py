import base64, json, sys, time, urllib.request
PROMPT = """You are a home battery installer reviewing a customer's photo of their electrical service panel.
Return ONLY JSON with these fields:
{"photo_type": "panel_open|panel_closed|meter_exterior|other", "cover_off": bool, "main_breaker_amps": int|null, "bus_rating_amps": int|null, "brand": str|null,
 "free_slots": int|null, "subpanel_visible": bool, "location": "indoor|outdoor|unknown", "gas_meter_within_3ft": bool|null, "clear_space_9ft": bool|null, "issues": [str],
 "pass": bool, "retake_reason": str|null, "confidence": 0-1}
Rules: main_breaker_amps only if you can read the number on the main breaker handle or label. issues = double taps, rust, water, missing knockouts, no label.
pass = true only if a configuration engineer could size the battery from this photo alone. retake_reason tells the customer exactly what to photograph again."""
def read(path, model="gemma4:e4b"):
    b = base64.b64encode(open(path,"rb").read()).decode()
    t = time.time()
    req = urllib.request.Request("http://localhost:11434/api/chat", data=json.dumps({"model": model, "stream": False, "format": "json",
        "messages": [{"role": "user", "content": PROMPT, "images": [b]}]}).encode(), headers={"Content-Type": "application/json"})
    out = json.loads(urllib.request.urlopen(req, timeout=300).read())["message"]["content"]
    return json.loads(out), round(time.time()-t, 1)
if __name__ == "__main__":
    out = open("pred_gemma4.jsonl", "a")
    for p in sys.argv[1:]:
        try: r, s = read(p)
        except Exception as e: r, s = {"error": str(e)}, 0
        out.write(json.dumps({"file": p.split("/")[-1], "secs": s, **r}) + "\n"); out.flush(); print(p, s, r.get("pass"), r.get("retake_reason"))
