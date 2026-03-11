# 🐾 Dogwatch IoT: Event-Driven Pet Safety System

**Dogwatch** is a robust, multi-layered IoT tracking and safety system designed to monitor pet location and safety in real-time. By leveraging a mesh network of LoRa-based Meshtastic nodes and a fleet of Bluetooth LE scanners, Dogwatch provides a highly reliable "geofence" that automatically fails over between long-range GPS and localized proximity detection.

## 🌟 Key Features

* **Event-Driven Architecture:** Built on a purely asynchronous MQTT backbone.
* **Hybrid Tracking:** Uses Meshtastic LoRa nodes for long-range GPS telemetry and Raspberry Pi Pico 2W nodes for localized Bluetooth LE proximity.
* **Protobuf Decoding:** Natively decodes binary Protocol Buffers directly from the MQTT stream for high-performance data handling.
* **Self-Healing Edge Nodes:** Implements hardware Watchdog Timers (WDT) on edge devices to ensure 100% uptime without manual intervention.
* **Modern Web Dashboard:** A JavaScript-driven, AJAX-powered frontend for real-time status updates.

---

## 🛠 Hardware Requirements

1. **Tracker Node:** 1x Meshtastic-compatible LoRa node (Recommended Node T1000-E).
2. **Base Station:** 1x Meshtastic node with Wi-Fi/Internet access.
3. **Proximity Nodes:** 1 or more Raspberry Pi Pico 2W boards.
4. **Bluetooth Tag:** 1x Standard BLE Beacon or a Meshtastic node with BLE enabled.
5. **Server:** Any Linux-based environment (Docker, VM, or Raspberry Pi) to host the Python backend.

---

## 📋 Prerequisites

* **MQTT Broker:** An active Mosquitto broker (or similar) reachable on your local network.
* **Meshtastic Config:** Base station must have **Encryption Disabled** and **Uplink Enabled** in the MQTT module settings.
* **Python 3.10+**: Required for the backend server.

---

## 🚀 Installation & Setup

### 1. Clone the Repository

```bash
git clone https://github.com/TannerOdenthal/dogwatch.git
cd dogwatch

```

### 2. Configure Environment Variables

Copy the example environment file and fill in your specific coordinates and API keys.

```bash
cp .env.example .env
nano .env

```

### 3. Install Dependencies

It is recommended to use a virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

```

### 4. Deploy Edge Nodes

* Flash the MicroPython firmware to your **Pico 2W**.
* [Edge Node Python Script](https://github.com/TannerOdenthal/dogwatchnode)
* Update the `ROOM_NAME` in the Pico script for each location (e.g., `kitchen`, `living_room`).
* Upload the script to the Pico as `main.py`.


---

## 🖥 Usage

### Running the Backend

Start the main application:

```bash
python main.py

```

The server will initialize three concurrent services:

1. **MQTT Listener:** Handles incoming LoRa and Bluetooth telemetry.
2. **State Evaluator:** Processes logic for safety status and alerts.
3. **Flask Web Server:** Serves the dashboard at `http://<your-ip>:5001`.

### Dashboard Controls

* **Armed Mode:** The default state. Alerts are triggered if the pet leaves the safe radius without a Bluetooth lock.
* **Travel Mode:** Temporarily silences alerts for a set duration (e.g., for walks).
* **Night Mode:** Automatically adjusts alert sensitivity during late-night hours.

---

## 🏗 Architecture Detail

The system utilizes a **State-Machine Logic** where safety is defined as:
`is_safe = (GPS_Distance < Safe_Radius) OR (ANY_Bluetooth_Node == Online)`

By decoupling the evaluation from the data intake, the system remains responsive even if one telemetry stream (like GPS) experiences high latency or signal degradation.

---

## 📝 License

This project is licensed under the MIT License - License file for details.

---
