import time
import math
import requests
import threading
import json
import paho.mqtt.client as mqtt
from datetime import datetime
from flask import Flask, request, render_template, jsonify

# Import Meshtastic Protobufs natively
from meshtastic import mesh_pb2, portnums_pb2, mqtt_pb2

# Import our centralized configuration
import config

# ==========================================
#              IN-MEMORY STATE
# ==========================================
receipt_user1 = None
receipt_user2 = None    
gps_out_count = 0
bt_out_count = 0
is_lost_mode = False
travel_mode_until = 0
alert_start_time = 0
alert_acknowledged = False

last_seen_time = "Never"
last_seen_dist = 0
last_seen_sats = 0
last_gps_update = 0
last_lat = 0.0
last_lon = 0.0
last_sent_lat = 0.0
last_sent_lon = 0.0
last_breadcrumb_time = 0

pico_fleet = {} 

# ==========================================
#           PUSHOVER ALERT HELPERS
# ==========================================
def send_pushover_alert(msg, user_key, priority="2", map_url=None):
    if not user_key or not config.PUSHOVER_API_TOKEN: 
        return None
        
    payload = {
        "token": config.PUSHOVER_API_TOKEN,
        "user": user_key,
        "message": msg,
        "title": "RENO ESCAPED!" if priority == "2" else "Reno Location Update",
        "priority": priority,
        "sound": "siren" if priority == "2" else "pushover"
    }
    
    if priority == "2":
        payload["retry"] = "30"
        payload["expire"] = "3600"
        
    if map_url:
        payload["url"] = map_url
        payload["url_title"] = "Open in Google Maps"

    try:
        r = requests.post("https://api.pushover.net/1/messages.json", data=payload)
        if r.status_code == 200:
            return r.json().get("receipt")
    except Exception as e:
        print(f"--> [ERROR] Failed to send Pushover alert: {e}")
    return None

def check_receipt_status(receipt):
    if not receipt or not config.PUSHOVER_API_TOKEN: 
        return False
    try:
        r = requests.get(f"https://api.pushover.net/1/receipts/{receipt}.json", params={"token": config.PUSHOVER_API_TOKEN})
        return r.json().get("acknowledged") == 1
    except Exception as e:
        print(f"--> [ERROR] Failed to check receipt status: {e}")
        return False

def cancel_pushover_alert(receipt):
    if not receipt or not config.PUSHOVER_API_TOKEN: 
        return
    try:
        requests.post(f"https://api.pushover.net/1/receipts/{receipt}/cancel.json", data={"token": config.PUSHOVER_API_TOKEN})
    except Exception as e:
        print(f"--> [ERROR] Failed to cancel Pushover alert: {e}")

# ==========================================
#              MQTT HANDLERS
# ==========================================
def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        print(f"--> [SUCCESS] Connected to MQTT Broker at {config.MQTT_BROKER}")
        client.subscribe("pico/proximity/#") 
        client.subscribe("msh/#")            
    else:
        print(f"--> [ERROR] MQTT Connection failed with code {rc}")

def on_message(client, userdata, msg):
    global pico_fleet, last_seen_time, last_seen_dist, last_seen_sats, last_gps_update, last_lat, last_lon
    
    # STREAM 1: Bluetooth Proximity Data
    if msg.topic.startswith("pico/proximity/"):
        try:
            topic_parts = msg.topic.split('/')
            if len(topic_parts) >= 4:
                room_name = topic_parts[2]
                data = json.loads(msg.payload.decode('utf-8'))
                
                if data.get("mac", "").lower() == config.TARGET_MAC.lower():
                    pico_fleet[room_name] = {
                        "status": data.get("status", "offline"),
                        "rssi": data.get("rssi", -100),
                        "last_ping": time.time()
                    }
        except Exception: pass

    # STREAM 2: Meshtastic GPS Data
    elif msg.topic.startswith("msh/") and config.TARGET_NODE_ID in msg.topic:
        try:
            env = mqtt_pb2.ServiceEnvelope()
            env.ParseFromString(msg.payload)
            mp = env.packet
            
            if mp.HasField("decoded") and mp.decoded.portnum == portnums_pb2.POSITION_APP:
                pos = mesh_pb2.Position()
                pos.ParseFromString(mp.decoded.payload)
                
                if pos.latitude_i and pos.longitude_i:
                    p_lat = pos.latitude_i / 10000000.0
                    p_lon = pos.longitude_i / 10000000.0
                    
                    last_lat = p_lat
                    last_lon = p_lon
                    last_seen_dist = int(get_distance(config.HOME_LAT, config.HOME_LON, p_lat, p_lon))
                    last_seen_sats = getattr(pos, 'sats_in_view', 0)
                    last_seen_time = datetime.now().strftime('%H:%M:%S')
                    last_gps_update = time.time()
        except Exception: pass 

def run_mqtt():
    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    
    if config.MQTT_USER and config.MQTT_PASS:
        client.username_pw_set(config.MQTT_USER, config.MQTT_PASS)
        
    client.on_connect = on_connect
    client.on_message = on_message
    
    while True:
        try:
            client.connect(config.MQTT_BROKER, 1883, 60)
            client.loop_forever()
        except Exception as e: 
            print(f"--> [RETRY] MQTT Broker unreachable: {e}")
            time.sleep(5)

# ==========================================
#              CORE LOGIC & HELPERS
# ==========================================
def get_distance(lat1, lon1, lat2, lon2):
    R = 6371000 
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi, dlambda = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

def get_fleet_status():
    is_bt_locked = False
    best_rssi = -100
    active_room = "Searching..."
    current_time = time.time()
    
    for room, state in pico_fleet.items():
        if (current_time - state["last_ping"]) < config.PROX_TIMEOUT:
            if state["status"] == "online":
                is_bt_locked = True
                if state["rssi"] > best_rssi:
                    best_rssi = state["rssi"]
                    active_room = room.replace("_", " ").title()
    return is_bt_locked, best_rssi, active_room

def state_evaluator_loop():
    global receipt_user1, receipt_user2, gps_out_count, bt_out_count, is_lost_mode, last_breadcrumb_time, last_sent_lat, last_sent_lon, alert_start_time, alert_acknowledged
    time.sleep(2) 

    while True:
        current_time = time.time()
        is_traveling = current_time < travel_mode_until
        is_night = 1 <= datetime.now().hour < 7
        
        bt_locked, _, active_room = get_fleet_status()
        gps_out = last_seen_dist > config.SAFE_RADIUS

        # Update independent failure counters
        if gps_out:
            gps_out_count += 1
        else:
            gps_out_count = 0

        if not bt_locked:
            bt_out_count += 1
        else:
            bt_out_count = 0

        # Define thresholds: Night mode is more tolerant of Bluetooth flickering
        gps_threshold = 2
        bt_threshold = 4 if is_night else 2

        if last_gps_update > 0:
            is_safe = not (gps_out_count >= gps_threshold and bt_out_count >= bt_threshold)
            status_str = "SAFE" if is_safe else "OUTSIDE"
            bt_str = f"BT-LOCKED [{active_room}]" if bt_locked else "BT-NONE"
            
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Mem-State: {last_seen_dist}m | Status: {status_str} ({bt_str}) | GPS-Fail: {gps_out_count}/{gps_threshold} | BT-Fail: {bt_out_count}/{bt_threshold}")

            # 1. PRIMARY ALERT (Escaped)
            if not is_safe and not is_traveling and not is_lost_mode:
                print(f"ALARM! {config.PET_NAME} is out.")
                is_lost_mode = True 
                alert_acknowledged = False
                alert_start_time = current_time
                receipt_user1 = send_pushover_alert(
                    f"{config.PET_NAME} escaped! {last_seen_dist}m away.", 
                    config.USER1_KEY, 
                    priority="2", 
                    map_url=f"https://www.google.com/maps/search/?api=1&query={last_lat},{last_lon}"
                )

            # 2. MONITOR ACKNOWLEDGMENT & ESCALATION
            if is_lost_mode and not alert_acknowledged:
                time_since_alert = int(current_time - alert_start_time)
                print(f"Monitoring ACK: {time_since_alert}s since alert. User2 Receipt: {receipt_user2}")
                
                # Check for acknowledgment from User 1 or User 2
                if check_receipt_status(receipt_user1) or check_receipt_status(receipt_user2):
                    print(f"ACK! Alert acknowledged for {config.PET_NAME}.")
                    alert_acknowledged = True
                    cancel_pushover_alert(receipt_user1)
                    cancel_pushover_alert(receipt_user2)
                    last_breadcrumb_time = 0 # Trigger immediate breadcrumb update after ack
                
                # Escalation to User 2 if not acknowledged within delay
                elif (current_time - alert_start_time) > config.ESCALATION_DELAY:
                    if not receipt_user2:
                        # Set a placeholder to prevent re-triggering if send fails or key is missing
                        receipt_user2 = "attempted" 
                        if config.USER2_KEY:
                            print(f"ESCALATION! Notifying {config.USER2_KEY} for {config.PET_NAME}.")
                            receipt_user2 = send_pushover_alert(
                                f"ESCALATION: {config.PET_NAME} is still missing! {last_seen_dist}m away.", 
                                config.USER2_KEY, 
                                priority="2", 
                                map_url=f"https://www.google.com/maps/search/?api=1&query={last_lat},{last_lon}"
                            )

            # 3. SAFE RETURN (Automatic Reset)
            if is_safe and is_lost_mode:
                print(f"SAFE! {config.PET_NAME} is back home.")
                cancel_pushover_alert(receipt_user1)
                cancel_pushover_alert(receipt_user2)
                
                if config.PUSHOVER_API_TOKEN and config.USER1_KEY:
                    send_pushover_alert(
                        f"SAFE! {config.PET_NAME} is back home and secure.", 
                        config.USER1_KEY, 
                        priority="0"
                    )
                
                is_lost_mode = False
                alert_acknowledged = False
                receipt_user1 = None
                receipt_user2 = None
                last_breadcrumb_time = 0

            # 4. ACTIVE TRACKING (Breadcrumbs for Travel or Lost Mode)
            if is_traveling or (is_lost_mode and alert_acknowledged):
                if (current_time - last_breadcrumb_time) >= config.BREADCRUMB_DELAY:
                    # Check if position has changed since last breadcrumb
                    if last_lat != last_sent_lat or last_lon != last_sent_lon:
                        label = "TRAVEL" if is_traveling else "LOST"
                        print(f"Tracking ({label}): {last_seen_dist}m away.")
                        
                        if config.PUSHOVER_API_TOKEN:
                            if last_lat != 0.0:
                                recipients = []
                                if config.SEND_BREADCRUMBS_USER1 and config.USER1_KEY:
                                    recipients.append(config.USER1_KEY)
                                if config.SEND_BREADCRUMBS_USER2 and config.USER2_KEY:
                                    recipients.append(config.USER2_KEY)
                                    
                                for user_key in recipients:
                                    send_pushover_alert(
                                        f"{label}: {config.PET_NAME} is {last_seen_dist}m away.",
                                        user_key,
                                        priority="-1", # Quiet Priority
                                        map_url=f"https://www.google.com/maps/search/?api=1&query={last_lat},{last_lon}"
                                    )
                                
                                last_breadcrumb_time = current_time
                                last_sent_lat = last_lat
                                last_sent_lon = last_lon
                            else:
                                print("Skipping breadcrumb: Waiting for first GPS coordinate.")
                    else:
                        # Location hasn't changed, just update time to wait for next window
                        last_breadcrumb_time = current_time
                
        time.sleep(config.CHECK_INTERVAL)

# ==========================================
#              WEB SERVER & API
# ==========================================
app = Flask(__name__)

@app.route('/')
def index():
    # Pass the pet name to the initial HTML render
    return render_template("index.html", pet_name=config.PET_NAME)

@app.route('/api/status')
def api_status():
    global travel_mode_until, last_seen_time, last_seen_dist, last_seen_sats
    
    rem = int((travel_mode_until - time.time()) / 60)
    is_night = 1 <= datetime.now().hour < 7
    bt_locked, best_rssi, active_room = get_fleet_status()
    rssi_pct = max(0, min(100, (best_rssi + 100) * 1.6)) if bt_locked else 0
    
    return jsonify({
        "traveling": rem > 0,
        "remaining_mins": rem,
        "night_mode": is_night,
        "last_seen": last_seen_time,
        "dist": last_seen_dist,
        "sats": last_seen_sats,
        "prox_on": bt_locked,
        "rssi": best_rssi,
        "rssi_pct": rssi_pct,
        "room": active_room
    })

@app.route('/set', methods=['POST'])
def set_mode():
    global travel_mode_until
    minutes = int(request.form.get('minutes', 60))
    travel_mode_until = time.time() + (minutes * 60)
    return jsonify({"status": "success", "mode": "travel"})

@app.route('/cancel', methods=['POST'])
def cancel_mode():
    global travel_mode_until, receipt_user1, receipt_user2, is_lost_mode, last_breadcrumb_time, alert_acknowledged, alert_start_time
    travel_mode_until = 0
    is_lost_mode = False
    alert_acknowledged = False
    alert_start_time = 0
    last_breadcrumb_time = 0
    
    if config.PUSHOVER_API_TOKEN:
        cancel_pushover_alert(receipt_user1)
        cancel_pushover_alert(receipt_user2)
        requests.post(f"https://api.pushover.net/1/receipts/cancel_all.json", data={"token": config.PUSHOVER_API_TOKEN})
        
    receipt_user1 = receipt_user2 = None
    return jsonify({"status": "success", "mode": "armed"})

if __name__ == "__main__":
    threading.Thread(target=run_mqtt, daemon=True).start()
    threading.Thread(target=lambda: app.run(host='0.0.0.0', port=5001, use_reloader=False), daemon=True).start()
    state_evaluator_loop()
