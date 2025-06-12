"""
Excel Exporter for Electric Meter Scraper
Scraper handles the data formatting, this excel_exporter.py module just exports the data.

"""

import os
import pandas as pd
from datetime import datetime


def export_to_excel(data, filename_prefix="data", sheets_config=None, output_dir=None):
    """
    Export data to an Excel file in a generic way.
    
    Args:
        data: The main data to export (dict, list, or DataFrame)
        filename_prefix: Prefix for the filename (default: "data")
        sheets_config: Dict with sheet configurations. Format:
                      {
                          "sheet_name": {
                              "data": data_for_sheet,
                              "index": False  # optional
                          }
                      }
        output_dir: Directory to save the file (default: calling script directory)
    
    Returns:
        str: Path to the saved Excel file, or None if failed
    """
    try:
        # Generate timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Determine output directory - same folder as the calling script
        if output_dir is None:
            import inspect
            caller_frame = inspect.currentframe().f_back
            caller_file = caller_frame.f_code.co_filename
            output_dir = os.path.dirname(os.path.abspath(caller_file))
        
        # Create filename
        excel_filename = f"{filename_prefix}_{timestamp}.xlsx"
        excel_file_path = os.path.join(output_dir, excel_filename)
        
        # Handle different data types
        if isinstance(data, pd.DataFrame):
            main_df = data
        elif isinstance(data, list):
            main_df = pd.DataFrame(data)
        elif isinstance(data, dict):
            main_df = pd.DataFrame([data])
        else:
            print(f"Warning: Unsupported data type {type(data)}, converting to DataFrame")
            main_df = pd.DataFrame([data])
        
        # Create Excel file
        with pd.ExcelWriter(excel_file_path, engine='openpyxl') as writer:
            # Save main data to first sheet
            main_df.to_excel(writer, index=False, sheet_name="Summary")
            
            # Save additional sheets if configured
            if sheets_config:
                for sheet_name, sheet_config in sheets_config.items():
                    sheet_data = sheet_config["data"]
                    include_index = sheet_config.get("index", False)
                    
                    if isinstance(sheet_data, pd.DataFrame):
                        sheet_df = sheet_data
                    elif isinstance(sheet_data, list):
                        sheet_df = pd.DataFrame(sheet_data)
                    elif isinstance(sheet_data, dict):
                        sheet_df = pd.DataFrame([sheet_data])
                    else:
                        sheet_df = pd.DataFrame([sheet_data])
                    
                    sheet_df.to_excel(writer, index=include_index, sheet_name=sheet_name)
        
        print(f"Data successfully exported to {excel_file_path}")
        return excel_file_path
        
    except Exception as e:
        print(f"Error exporting data to Excel: {e}")
        return None


def export_imagine_data(usage_data):
    """
    Export Imagine usage data to Excel with proper formatting.
    
    Args:
        usage_data: Dictionary containing Imagine usage data
    
    Returns:
        str: Path to the saved Excel file, or None if failed
    """
    if not usage_data:
        print("No Imagine usage data provided to export")
        return None
    
    print("Preparing to export Imagine data to Excel...")
    
    # Prepare breakdown data if available
    sheets_config = {}
    if "Base Plan Usage" in usage_data or "Topup Usage" in usage_data:
        breakdown_data = []
        if "Base Plan Usage" in usage_data:
            breakdown_data.append({
                "Plan Type": "Base Plan",
                "Usage Info": usage_data["Base Plan Usage"],
                "Total Allowance": usage_data.get("Base Plan Total", "N/A")
            })
        if "Topup Usage" in usage_data:
            breakdown_data.append({
                "Plan Type": "Topup",
                "Usage Info": usage_data["Topup Usage"], 
                "Total Allowance": usage_data.get("Topup Total", "N/A"),
                "Expiry": usage_data.get("Topup Expiry", "N/A")
            })
        
        sheets_config["Usage Breakdown"] = {"data": breakdown_data}
    
    return export_to_excel(
        data=usage_data,
        filename_prefix="ImagineUsageData",
        sheets_config=sheets_config
    )


def export_usms_data(hourly_consumption, total_kwh=None, dynamic_values=None, all_meter_data=None):
    """
    Export USMS meter data to Excel with proper formatting.
    
    Args:
        hourly_consumption: List of hourly consumption data
        total_kwh: Total consumption value
        dynamic_values: Dictionary of dynamic values (Remaining Unit, Balance, etc.)
        all_meter_data: Dictionary containing electricity and water meter data
    
    Returns:
        str: Path to the saved Excel file, or None if failed
    """
    if not hourly_consumption and not all_meter_data:
        print("No USMS data provided to export")
        return None
    
    print("Preparing to export USMS data to Excel...")
    
    # Prepare additional sheets
    sheets_config = {}
    
    # Add summary sheet with totals and dynamic values
    if total_kwh or dynamic_values:
        summary_data = {}
        if total_kwh:
            summary_data["Total Consumption (kWh)"] = total_kwh
        if dynamic_values:
            summary_data.update(dynamic_values)
        
        sheets_config["Account Summary"] = {"data": summary_data}
    
    # Add meter information sheets
    if all_meter_data:
        if 'electricity' in all_meter_data:
            sheets_config["Electricity Meter"] = {"data": all_meter_data['electricity']}
        if 'water' in all_meter_data:
            sheets_config["Water Meter"] = {"data": all_meter_data['water']}
    
    # Use hourly consumption as main data if available, otherwise use meter data
    main_data = hourly_consumption if hourly_consumption else all_meter_data
    
    return export_to_excel(
        data=main_data,
        filename_prefix="MeterData",
        sheets_config=sheets_config
    )
