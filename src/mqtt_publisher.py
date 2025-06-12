import paho.mqtt.client as mqtt
import json
import os
import time  # Added import for time
from datetime import datetime, timezone, timedelta

"""
MQTT Publisher for Home Assistant Integration

This module provides a shared MQTT utility for publishing scraper data to Home Assistant.
Designed to be used by both usmsScraper.py (USMS) and imagineScraper.py (Imagine) scrapers.

SIMPLIFIED ARCHITECTURE OVERVIEW:
===============================
- Shared MQTT module (this file) handles all MQTT communication
- Individual scrapers call this module after successful data scraping
- Graceful degradation: if MQTT fails, scrapers continue with Excel export
- Simple JSON publishing: Only 2 topics total (one per service)
- Home Assistant will parse JSON payloads using value_json templates

Scraper handles the data formtting, this mqtt_publisher.py module just sends the data.

"""

def load_mqtt_config():
    credentials_path = os.path.join(os.path.dirname(__file__), 'credentials.json')
    try:
        with open(credentials_path, 'r') as f:
            creds = json.load(f)
        mqtt_config = creds.get('mqtt')
        if not mqtt_config:
            print("MQTT configuration not found in credentials.json")
            return None
        # Basic validation for essential keys
        required_keys = ["broker", "port", "username", "password", "base_topic"]
        for key in required_keys:
            if key not in mqtt_config:
                print(f"MQTT config missing required key: {key}")
                return None
        return mqtt_config
    except FileNotFoundError:
        print(f"credentials.json not found at {credentials_path}")
        return None
    except json.JSONDecodeError:
        print("Error decoding JSON from credentials.json")  # Removed f-string
        return None
    except Exception as e:
        print(f"Error loading MQTT config: {e}")
        return None

def publish_service_json(service_path, data_dict): # Renamed service_name to service_path
    config = load_mqtt_config()
    if not config:
        print("MQTT configuration not available for publishing.")
        return False

    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    client.username_pw_set(config['username'], config['password'])

    # Construct the topic using base_topic from config and the provided service_path
    topic = f"{config['base_topic']}/{service_path}"
    
    data_dict_with_ts = data_dict.copy()
    
    if 'mqtt_timestamp' not in data_dict_with_ts:
        # Convert to Brunei time (UTC+8) with proper timezone info
        utc_now = datetime.now(timezone.utc)
        brunei_tz = timezone(timedelta(hours=8))
        brunei_now = utc_now.astimezone(brunei_tz)
        data_dict_with_ts['mqtt_timestamp'] = brunei_now.isoformat()

    try:
        payload = json.dumps(data_dict_with_ts)
    except TypeError as e:
        print(f"Error serializing data to JSON: {e}")
        return False

    status = {'connected': False, 'published': False, 'disconnect_reason': None}

    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            print(f"Successfully connected to MQTT broker for publishing to {topic}.")
            status['connected'] = True
        else:
            print(f"Failed to connect to MQTT broker. Return code: {reason_code}")
            status['connected'] = False

    def on_disconnect(client, userdata, flags, reason_code, properties):
        rc_value = reason_code.value if hasattr(reason_code, 'value') else reason_code
        print(f"Disconnected from MQTT broker. Reason code: {rc_value}")
        status['disconnect_reason'] = rc_value

    def on_publish(client, userdata, mid, reason_code, properties):
        is_v5_success = hasattr(reason_code, 'value') and reason_code.value == 0
        is_legacy_success = reason_code == 0 or reason_code is None

        if is_v5_success or is_legacy_success:
            print(f"Message {mid} published successfully to {topic}.")
            status['published'] = True
        else:
            rc_value = reason_code.value if hasattr(reason_code, 'value') else reason_code
            print(f"Failed to publish message {mid} to {topic}. Reason code: {rc_value}")
            status['published'] = False

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_publish = on_publish

    try:
        print(f"Attempting to connect to {config['broker']}:{config['port']} to publish on {topic}")
        client.connect(config['broker'], config['port'], 60)
        client.loop_start() 

        connect_timeout = time.time() + 10
        while not status['connected'] and time.time() < connect_timeout:
            if status['connected'] is False and status['disconnect_reason'] is not None:
                 print("Connection explicitly failed by on_connect callback.")
                 break
            time.sleep(0.1)
        
        if not status['connected']:
            print("Connection to MQTT broker failed or timed out.")
            return False

        print(f"Publishing message to {topic}: {payload}")
        retain_flag = bool(config.get('retain_messages', False))
        msg_info = client.publish(topic, payload, qos=1, retain=retain_flag)
        
        if msg_info.rc != mqtt.MQTT_ERR_SUCCESS:
            print(f"Publish command failed immediately with RC: {msg_info.rc}")
            return False

        publish_timeout = time.time() + 10
        while not status['published'] and time.time() < publish_timeout:
            time.sleep(0.1)

        if not status['published']:
            print(f"Publish confirmation not received for message {msg_info.mid} (rc={msg_info.rc}).")
            return False
        
        return True

    except Exception as e:
        print(f"Error during MQTT operation: {e}")
        return False
    finally:
        if client:
            client.loop_stop()
            if hasattr(client, '_sock') and client._sock is not None:
                 try:
                    client.disconnect()
                 except Exception as e:
                    print(f"Error during disconnect: {e}")
            elif hasattr(client, 'is_connected') and client.is_connected():
                 try:
                    client.disconnect()
                 except Exception as e:
                    print(f"Error during disconnect (is_connected): {e}")
            print("MQTT client loop stopped and disconnect attempt finished.")

def publish_usms_json(electricity_data, water_data):
    print("Preparing to publish USMS data to separate topics...")
    overall_success = True
    current_timestamp = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8))).isoformat()

    # Publish Electricity Data
    if electricity_data:
        print("Publishing USMS Electricity Data...")
        # Ensure a consistent timestamp, preferably added by the scraper, but fallback here.
        if 'mqtt_timestamp' not in electricity_data:
            electricity_data['mqtt_timestamp'] = current_timestamp
        
        if not publish_service_json("usms/electric", electricity_data): # Changed topic here
            print("❌ Failed to publish USMS Electricity data.")
            overall_success = False
        # No explicit success print here, publish_service_json handles it
    else:
        print("No electricity data to publish for USMS.")

    # Publish Water Data
    if water_data:
        print("Publishing USMS Water Data...")
        if 'mqtt_timestamp' not in water_data:
            water_data['mqtt_timestamp'] = current_timestamp

        if not publish_service_json("usms/water", water_data):
            print("❌ Failed to publish USMS Water data.")
            overall_success = False
        # No explicit success print here, publish_service_json handles it
    else:
        print("No water data to publish for USMS.")

    return overall_success

def publish_imagine_json(data_dict):
    print("Preparing to publish Imagine data (pre-formatted by scraper)...")
    
    # Validate that the expected keys are present and are integers
    if not isinstance(data_dict.get('base_plan_used_gb'), int) or \
       not isinstance(data_dict.get('base_plan_total_gb'), int):
        print(f"Error: Data for Imagine is not in the expected format. Received: {data_dict}")
        print("Expected format: {'base_plan_used_gb': <int>, 'base_plan_total_gb': <int>}")
        return False
        
    payload_to_publish = {
        'base_plan_used': data_dict['base_plan_used_gb'],
        'base_plan_total': data_dict['base_plan_total_gb']
    }
    
    return publish_service_json("imagine", payload_to_publish)
