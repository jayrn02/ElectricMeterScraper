import paho.mqtt.client as mqtt
import json
import os
import time  # Added import for time
from datetime import datetime

"""
MQTT Publisher for Home Assistant Integration

This module provides a shared MQTT utility for publishing scraper data to Home Assistant.
Designed to be used by both scraper.py (USMS) and imagineScraper.py (Imagine) scrapers.

SIMPLIFIED ARCHITECTURE OVERVIEW:
===============================
- Shared MQTT module (this file) handles all MQTT communication
- Individual scrapers call this module after successful data scraping
- Graceful degradation: if MQTT fails, scrapers continue with Excel export
- Simple JSON publishing: Only 2 topics total (one per service)
- Home Assistant will parse JSON payloads using value_json templates

SIMPLIFIED APPROACH:
==================
Instead of multiple individual sensor topics, we publish complete service data as JSON:

Topic 1: "homeassistant/usms/data" 
Topic 2: "homeassistant/imagine/data"

Each topic contains ALL data for that service in a single JSON payload.
Home Assistant will extract individual sensor values using value_json templates.

TASKS TO IMPLEMENT:
==================

1. CONFIGURATION MANAGEMENT:
   - Load MQTT broker settings from credentials.json
   - Support for broker host, port, username, password
   - Optional TLS/SSL configuration
   - Simple topic structure: just 2 base topics

2. CONNECTION HANDLING:
   - Establish MQTT connection with error handling
   - Basic retry logic for failed connections
   - Graceful handling of broker unavailability
   - Simple connect-publish-disconnect pattern

3. JSON DATA PUBLISHING:
   
   A. USMS (Electric Meter) JSON:
      - publish_usms_json(data_dict)
      - Single topic: "homeassistant/usms/data"
      - JSON payload contains ALL USMS data
      - Raw data from scraper converted to structured JSON
   
   B. Imagine (Internet) JSON:
      - publish_imagine_json(data_dict)
      - Single topic: "homeassistant/imagine/data"
      - JSON payload contains ALL Imagine data
      - Parsed usage strings included in JSON structure
   
   C. Generic JSON Publisher:
      - publish_service_json(service_name, data_dict)
      - Handles JSON serialization and MQTT publishing
      - Timestamp injection for last_updated fields

4. DATA TRANSFORMATION (MINIMAL):
   - Convert scraper data_dict to clean JSON structure
   - Parse Imagine usage strings: "139GB of 700 GB Used" -> extract numbers
   - Add timestamp for when data was published
   - Validate JSON structure before publishing

5. ERROR HANDLING & LOGGING:
   - Basic exception handling for MQTT operations
   - Logging for debugging and monitoring
   - Fallback: continue scraper execution if MQTT fails
   - Status reporting back to calling scrapers

6. HOME ASSISTANT INTEGRATION:
   - HA will create sensors using value_json templates
   - Manual sensor configuration in HA (no auto-discovery needed)
   - Simple topic structure reduces complexity
   - JSON payloads are human-readable for debugging

INTEGRATION POINTS:
==================

From scraper.py (USMS):
```python
from mqtt_publisher import publish_usms_json

# After successful scraping...
try:
    publish_usms_json({
        'remaining_units': '123.45',
        'remaining_balance': 'BND 67.89', 
        'last_updated': '2025-06-07 13:40:12',
        'hourly_data': hourly_consumption_list,
        'total_consumption': '18.240'
    })
    print("USMS data published to MQTT as JSON")
except Exception as e:
    print(f"MQTT publish failed, continuing with Excel only: {e}")
```

From imagineScraper.py (Imagine):
```python
from mqtt_publisher import publish_imagine_json

# After successful scraping...
try:
    publish_imagine_json({
        'base_plan_usage': '139GB of 700 GB Used',
        'topup_usage': '60GB of 60GB Used',
        'base_plan_total': '700 GB',
        'topup_total': '60GB',
        'topup_expiry': 'Expiry: 18 Jun 2025'
    })
    print("Imagine data published to MQTT as JSON")
except Exception as e:
    print(f"MQTT publish failed, continuing with Excel only: {e}")
```

MQTT TOPICS STRUCTURE:
=====================
Only 2 topics total:

Topic 1: "homeassistant/usms/data"
JSON Payload Example:
{
    "remaining_units": 123.45,
    "remaining_balance": 67.89,
    "remaining_balance_raw": "BND 67.89",
    "last_updated": "2025-06-07T13:40:12",
    "total_consumption": 18.240,
    "hourly_data": [
        {"hour": "00:00", "consumption_kWh": 2.5},
        {"hour": "01:00", "consumption_kWh": 1.8}
    ],
    "mqtt_timestamp": "2025-06-07T13:45:30"
}

Topic 2: "homeassistant/imagine/data"  
JSON Payload Example:
{
    "base_plan_used_gb": 139,
    "base_plan_total_gb": 700,
    "base_plan_usage_raw": "139GB of 700 GB Used",
    "topup_used_gb": 60,
    "topup_total_gb": 60,
    "topup_usage_raw": "60GB of 60GB Used",
    "topup_expiry_date": "2025-06-18",
    "topup_expiry_raw": "Expiry: 18 Jun 2025",
    "mqtt_timestamp": "2025-06-07T13:45:30"
}

CONFIGURATION EXAMPLE:
=====================
Add to credentials.json:
{
  "mqtt": {
    "broker": "homeassistant.local", 
    "port": 1883,
    "username": "mqtt_user",
    "password": "mqtt_pass",
    "base_topic": "homeassistant",
    "retain_messages": false
  }
}

HOME ASSISTANT SENSOR CONFIGURATION:
===================================
In Home Assistant configuration.yaml, create sensors using value_json:

```yaml
mqtt:
  sensor:
    # USMS Sensors
    - name: "USMS Remaining Units"
      state_topic: "homeassistant/usms/data"
      value_template: "{{ value_json.remaining_units }}"
      unit_of_measurement: "kWh"
      device_class: energy
      
    - name: "USMS Remaining Balance" 
      state_topic: "homeassistant/usms/data"
      value_template: "{{ value_json.remaining_balance }}"
      unit_of_measurement: "BND"
      
    - name: "USMS Last Updated"
      state_topic: "homeassistant/usms/data" 
      value_template: "{{ value_json.last_updated }}"
      device_class: timestamp
      
    # Imagine Sensors
    - name: "Imagine Base Plan Used"
      state_topic: "homeassistant/imagine/data"
      value_template: "{{ value_json.base_plan_used_gb }}"
      unit_of_measurement: "GB"
      
    - name: "Imagine Base Plan Total"
      state_topic: "homeassistant/imagine/data"
      value_template: "{{ value_json.base_plan_total_gb }}"
      unit_of_measurement: "GB"
      
    - name: "Imagine Topup Expiry"
      state_topic: "homeassistant/imagine/data"
      value_template: "{{ value_json.topup_expiry_date }}"
      device_class: timestamp
```

ADVANTAGES OF JSON APPROACH:
===========================
- Only 2 MQTT topics to manage (simple)
- All related data published atomically 
- Human-readable JSON for debugging
- Flexible: can add new fields without changing topics
- Reduced MQTT broker load (fewer messages)
- Raw data preserved alongside parsed values
- Single timestamp for entire service data update

FUTURE ENHANCEMENTS:
===================
- Support for additional scrapers (new JSON topics)
- Historical data republishing as JSON arrays
- JSON schema validation
- Compression for large JSON payloads
- Custom JSON field mapping configuration
- Batch publishing multiple service updates
"""

# TODO: Implement all the functions outlined above
# This file currently serves as a blueprint and dependency placeholder

def load_mqtt_config():
    """
    Load MQTT configuration from credentials.json
    Returns: dict with broker, port, username, password, base_topic, retain_messages
             Returns None if config is not found or file is missing.
    """
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

def test_mqtt_connection():
    """
    Test MQTT broker connectivity using credentials from credentials.json
    Returns: bool indicating success/failure
    """
    config = load_mqtt_config()
    if not config:
        print("MQTT configuration not available for connection test.")
        return False

    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    client.username_pw_set(config['username'], config['password'])

    connection_successful = False

    def on_connect(client, userdata, flags, reason_code, properties):
        nonlocal connection_successful
        if reason_code == 0:
            print("Connection test: Successfully connected to MQTT broker.")
            connection_successful = True
        else:
            print(f"Connection test: Failed to connect. Return code: {reason_code}")
        client.disconnect() # Disconnect after checking

    def on_disconnect(client, userdata, flags, reason_code, properties):
        print("Connection test: Disconnected.")

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect

    try:
        print(f"Connection test: Attempting to connect to {config['broker']}:{config['port']}")
        client.connect(config['broker'], config['port'], 60)
        client.loop_start() # Start loop to process callbacks
        time.sleep(2)  # Give time for connection attempt and callback
        client.loop_stop()
    except Exception as e:
        print(f"Connection test: Error during connection: {e}")
        return False
    
    return connection_successful

def publish_usms_json(data_dict):
    """
    Publish complete USMS data as single JSON message
    TODO: Implement USMS JSON publishing to "homeassistant/usms/data"
    
    Args:
        data_dict: Raw data from USMS scraper
    
    Expected transformations:
        - Convert string numbers to floats
        - Parse "BND 67.89" to extract 67.89
        - Add mqtt_timestamp
        - Structure hourly_data as JSON array
    """
    pass

def publish_imagine_json(data_dict):
    """
    Publish complete Imagine data as single JSON message  
    TODO: Implement Imagine JSON publishing to "homeassistant/imagine/data"
    
    Args:
        data_dict: Raw data from Imagine scraper
        
    Expected transformations:
        - Parse "139GB of 700 GB Used" -> extract 139 and 700
        - Parse "Expiry: 18 Jun 2025" -> convert to "2025-06-18"
        - Convert GB strings to numbers
        - Add mqtt_timestamp
        - Preserve raw strings alongside parsed values
    """
    pass

def publish_service_json(service_name, data_dict):
    """
    Generic JSON publisher for any service
    TODO: Implement generic MQTT JSON publishing
    
    Args:
        service_name: "usms" or "imagine" 
        data_dict: Service data to publish
        
    Publishes to: "homeassistant/{service_name}/data"
    """
    pass

def _parse_imagine_usage(usage_string):
    """
    Helper function to parse Imagine usage strings
    TODO: Implement parsing logic for "139GB of 700 GB Used" format
    
    Args:
        usage_string: String like "139GB of 700 GB Used"
        
    Returns:
        tuple: (used_gb, total_gb) as integers
    """
    pass

def _parse_date_string(date_string):
    """
    Helper function to parse date strings
    TODO: Implement date parsing for "Expiry: 18 Jun 2025" format
    
    Args:
        date_string: String like "Expiry: 18 Jun 2025"
        
    Returns:
        str: ISO date format "2025-06-18"
    """
    pass
