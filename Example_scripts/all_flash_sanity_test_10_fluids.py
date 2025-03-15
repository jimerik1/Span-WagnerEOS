import requests
import pandas as pd
import numpy as np
import time
from tabulate import tabulate

# API base URL - adjust if your API is hosted elsewhere
BASE_URL = "http://localhost:5051"

def sanity_check_eos():
    """
    Comprehensive sanity check of the Span-Wagner EOS API by comparing PT-flash, PH-flash, and TS-flash results.
    
    This function:
    1. Calculates thermodynamic properties using PT-flash at various pressure and temperature points
    2. Uses the resulting enthalpy with the same pressure in PH-flash
    3. Uses the resulting entropy with the same temperature in TS-flash
    4. Compares all properties across the three calculations to verify consistency
    
    Properties compared include:
    - Temperature, pressure, and density (primary validation)
    - Internal energy, enthalpy, entropy
    - Heat capacities (Cv, Cp)
    - Sound speed, compressibility factor
    - Transport properties (viscosity, thermal conductivity)
    
    This comprehensive validation ensures that the EOS implementation is thermodynamically 
    consistent across different flash calculation routes.
    """
    print("Starting REFPROP API Sanity Check")
    print("=" * 80)
    
    # Define 10 different fluid compositions for testing
    fluid_compositions = [
        [
            {"fluid": "CO2", "fraction": 0.90},
            {"fluid": "METHANE", "fraction": 0.10}
        ],
        [
            {"fluid": "METHANE", "fraction": 0.85},
            {"fluid": "ETHANE", "fraction": 0.10},
            {"fluid": "PROPANE", "fraction": 0.05}
        ],
        [
            {"fluid": "NITROGEN", "fraction": 0.78},
            {"fluid": "OXYGEN", "fraction": 0.21},
            {"fluid": "ARGON", "fraction": 0.01}
        ],
        [
            {"fluid": "WATER", "fraction": 1.0}
        ],
        [
            {"fluid": "HYDROGEN", "fraction": 1.0}
        ],
        [
            {"fluid": "R134A", "fraction": 1.0}
        ],
        [
            {"fluid": "PROPANE", "fraction": 0.60},
            {"fluid": "BUTANE", "fraction": 0.40}
        ],
        [
            {"fluid": "OXYGEN", "fraction": 0.50},
            {"fluid": "NITROGEN", "fraction": 0.50}
        ],
        [
            {"fluid": "AMMONIA", "fraction": 1.0}
        ],
        [
            {"fluid": "ETHANE", "fraction": 0.40},
            {"fluid": "PROPANE", "fraction": 0.35},
            {"fluid": "BUTANE", "fraction": 0.25}
        ]
    ]
    
    # Description of each fluid composition for reporting
    composition_descriptions = [
        "CO2-Methane mixture (90%-10%)",
        "Natural gas mixture (Methane-Ethane-Propane)",
        "Air (Nitrogen-Oxygen-Argon)",
        "Pure Water",
        "Pure Hydrogen",
        "Pure R134a (refrigerant)",
        "LPG mixture (Propane-Butane)",
        "Oxygen-Nitrogen mixture (50%-50%)",
        "Pure Ammonia",
        "Hydrocarbon mixture (Ethane-Propane-Butane)"
    ]
    
    # Test points per fluid composition
    points_per_fluid = 5  # Reduced number of points per fluid to keep total runtime reasonable
    
    print(f"Testing {len(fluid_compositions)} different fluid compositions with {points_per_fluid} points each")
    print(f"Total test points: {len(fluid_compositions) * points_per_fluid}")
    
    # Function to generate appropriate test points for each fluid
    def generate_test_points_for_fluid(fluid_index):
        fluid = fluid_compositions[fluid_index]
        fluid_desc = composition_descriptions[fluid_index]
        
        # Adjust ranges based on fluid type to ensure physically relevant test points
        if "WATER" in [comp["fluid"] for comp in fluid]:
            # Water has a higher critical point and wider range
            pressures = np.linspace(1, 220, 5)  
            temperatures = np.linspace(5, 350, 3)
        elif "HYDROGEN" in [comp["fluid"] for comp in fluid]:
            # Hydrogen has a very low critical point
            pressures = np.linspace(1, 80, 5)
            temperatures = np.linspace(-250, -210, 3)
        elif "R134A" in [comp["fluid"] for comp in fluid]:
            # R134a refrigerant typical range
            pressures = np.linspace(1, 40, 5)
            temperatures = np.linspace(-40, 70, 3)
        elif "AMMONIA" in [comp["fluid"] for comp in fluid]:
            # Ammonia typical range
            pressures = np.linspace(1, 60, 5)
            temperatures = np.linspace(-40, 100, 3)
        else:
            # Default range for most fluids
            pressures = np.linspace(1, 150, 5)
            temperatures = np.linspace(-50, 100, 3)
        
        test_points = []
        for pressure in pressures[:points_per_fluid]:
            for temperature in temperatures[:2]:  # Limit to prevent too many points
                if len(test_points) < points_per_fluid:
                    test_points.append({
                        "pressure": round(pressure, 1),
                        "temperature": round(temperature, 1),
                        "fluid_index": fluid_index
                    })
        
        print(f"Generated {len(test_points)} test points for {fluid_desc}")
        return test_points
    
    # Generate test points for all fluids
    all_test_points = []
    for i in range(len(fluid_compositions)):
        all_test_points.extend(generate_test_points_for_fluid(i))
    
    print(f"Total generated test points: {len(all_test_points)}")

    # Part 1: PT-flash calculations
    # Create batched PT-flash requests to optimize API calls
    batch_size = 10  # Adjust based on API performance
    pt_batches = [all_test_points[i:i + batch_size] for i in range(0, len(all_test_points), batch_size)]
    
    pt_results = []
    print("Running PT-flash calculations...")
    
    for batch_idx, batch in enumerate(pt_batches, 1):
        print(f"Processing PT-flash batch {batch_idx}/{len(pt_batches)}...")
        
        # For each point in the batch, prepare a single PT-flash call with narrow ranges
        for point in batch:
            # Get the appropriate composition for this test point
            fluid_index = point["fluid_index"]
            current_composition = fluid_compositions[fluid_index]
            fluid_desc = composition_descriptions[fluid_index]
            
            # Prepare the PT-flash request payload
            pt_payload = {
                "composition": current_composition,
                "pressure_range": {
                    "from": point["pressure"],
                    "to": point["pressure"]
                },
                "temperature_range": {
                    "from": point["temperature"],
                    "to": point["temperature"]
                },
                "pressure_resolution": 1,
                "temperature_resolution": 1,
                "properties": [
                    "density",
                    "enthalpy",
                    "internal_energy",
                    "entropy",
                    "Cv",
                    "Cp",
                    "sound_speed",
                    "compressibility_factor",
                    "phase",
                    "vapor_fraction",
                    "viscosity",
                    "thermal_conductivity"
                ],
                "units_system": "SI"
            }
            
            # Send the PT-flash request
            try:
                response = requests.post(f"{BASE_URL}/pt_flash", json=pt_payload, timeout=30)
                response.raise_for_status()
                
                # Extract results
                result = response.json()["results"][0]
                
                # Extract all available properties from PT-flash
                pt_result = {
                    "pressure": point["pressure"],
                    "temperature": point["temperature"],
                    "fluid_index": fluid_index,
                    "fluid_desc": fluid_desc,
                    "density": result["density"]["value"],
                    "enthalpy": result["enthalpy"]["value"],
                    "entropy": result["entropy"]["value"],
                    "phase": result["phase"]["value"],
                    "vapor_fraction": result["vapor_fraction"]["value"]
                }
                
                # Add all additional properties that were requested
                for prop in ["internal_energy", "Cv", "Cp", "sound_speed", 
                            "compressibility_factor", "viscosity", "thermal_conductivity"]:
                    if prop in result:
                        pt_result[prop] = result[prop]["value"]
                
                pt_results.append(pt_result)
                print(f"PT-flash completed for fluid: {fluid_desc}, P={point['pressure']} bar, T={point['temperature']}°C, Phase={pt_result['phase']}")
                
            except Exception as e:
                print(f"Error in PT-flash calculation for fluid: {fluid_desc}, P={point['pressure']} bar, T={point['temperature']}°C: {str(e)}")
                continue
                
        # Brief pause between batches to avoid overwhelming the API
        if batch_idx < len(pt_batches):
            time.sleep(0.5)
    
    # Pause to avoid overloading the API
    time.sleep(1)
    
    # Part 2: PH-flash calculations using the enthalpy from PT-flash
    ph_results = []
    print("\nRunning PH-flash calculations with enthalpy from PT-flash...")
    
    # Create batches for PH-flash as well
    ph_batches = [pt_results[i:i + batch_size] for i in range(0, len(pt_results), batch_size)]
    
    for batch_idx, batch in enumerate(ph_batches, 1):
        print(f"Processing PH-flash batch {batch_idx}/{len(ph_batches)}...")
        
        for pt_result in batch:
            # Get the appropriate composition for this test point
            fluid_index = pt_result["fluid_index"]
            current_composition = fluid_compositions[fluid_index]
            fluid_desc = pt_result["fluid_desc"]
            
            # Prepare the PH-flash request payload
            ph_payload = {
                "composition": current_composition,
                "pressure_range": {
                    "from": pt_result["pressure"],
                    "to": pt_result["pressure"]
                },
                "enthalpy_range": {
                    "from": pt_result["enthalpy"],
                    "to": pt_result["enthalpy"]
                },
                "pressure_resolution": 1,
                "enthalpy_resolution": 1,
                "properties": [
                    "temperature",
                    "density",
                    "internal_energy",
                    "entropy",
                    "Cv",
                    "Cp",
                    "sound_speed",
                    "compressibility_factor",
                    "phase",
                    "vapor_fraction",
                    "viscosity",
                    "thermal_conductivity"
                ],
                "units_system": "SI"
            }
            
            # Send the PH-flash request
            try:
                response = requests.post(f"{BASE_URL}/ph_flash", json=ph_payload, timeout=30)
                response.raise_for_status()
                
                # Extract results
                result = response.json()["results"][0]
                
                # Initialize with basic properties
                ph_result = {
                    "pressure": pt_result["pressure"],
                    "enthalpy": pt_result["enthalpy"],
                    "temperature": result["temperature"]["value"],
                    "density": result["density"]["value"],
                    "entropy": result["entropy"]["value"],
                    "phase": result["phase"]["value"],
                    "vapor_fraction": result["vapor_fraction"]["value"],
                    "original_temperature": pt_result["temperature"],
                    "original_density": pt_result["density"],
                    "original_entropy": pt_result["entropy"],
                    "fluid_index": fluid_index,
                    "fluid_desc": fluid_desc
                }
                
                # Add all additional properties for comparison
                for prop in ["internal_energy", "Cv", "Cp", "sound_speed", 
                            "compressibility_factor", "viscosity", "thermal_conductivity"]:
                    if prop in result and prop in pt_result:
                        ph_result[prop] = result[prop]["value"]
                        ph_result[f"original_{prop}"] = pt_result[prop]
                
                ph_results.append(ph_result)
                print(f"PH-flash completed for fluid: {fluid_desc}, P={pt_result['pressure']} bar, H={pt_result['enthalpy']:.2f} J/mol")
                
            except Exception as e:
                print(f"Error in PH-flash calculation for fluid: {fluid_desc}, P={pt_result['pressure']} bar, H={pt_result['enthalpy']:.2f} J/mol: {str(e)}")
                continue
        
        # Brief pause between batches
        if batch_idx < len(ph_batches):
            time.sleep(0.5)
    
    # Pause to avoid overloading the API
    time.sleep(1)
    
    # Part 3: TS-flash calculations using the entropy from PT-flash
    ts_results = []
    print("\nRunning TS-flash calculations with entropy from PT-flash...")
    
    # Create batches for TS-flash as well
    ts_batches = [pt_results[i:i + batch_size] for i in range(0, len(pt_results), batch_size)]
    
    for batch_idx, batch in enumerate(ts_batches, 1):
        print(f"Processing TS-flash batch {batch_idx}/{len(ts_batches)}...")
        
        for pt_result in batch:
            # Get the appropriate composition for this test point
            fluid_index = pt_result["fluid_index"]
            current_composition = fluid_compositions[fluid_index]
            fluid_desc = pt_result["fluid_desc"]
            
            # Prepare the TS-flash request payload
            ts_payload = {
                "composition": current_composition,
                "temperature_range": {
                    "from": pt_result["temperature"],
                    "to": pt_result["temperature"]
                },
                "entropy_range": {
                    "from": pt_result["entropy"],
                    "to": pt_result["entropy"]
                },
                "temperature_resolution": 1,
                "entropy_resolution": 1,
                "properties": [
                    "pressure",
                    "density",
                    "internal_energy",
                    "enthalpy",
                    "Cv",
                    "Cp",
                    "sound_speed",
                    "compressibility_factor",
                    "phase",
                    "vapor_fraction",
                    "viscosity",
                    "thermal_conductivity"
                ],
                "units_system": "SI"
            }
            
            # Send the TS-flash request
            try:
                response = requests.post(f"{BASE_URL}/ts_flash", json=ts_payload, timeout=30)
                response.raise_for_status()
                
                # Extract results
                result = response.json()["results"][0]
                
                # Initialize with basic properties
                ts_result = {
                    "temperature": pt_result["temperature"],
                    "entropy": pt_result["entropy"],
                    "pressure": result["pressure"]["value"],
                    "density": result["density"]["value"],
                    "enthalpy": result["enthalpy"]["value"],
                    "phase": result["phase"]["value"],
                    "vapor_fraction": result["vapor_fraction"]["value"],
                    "original_pressure": pt_result["pressure"],
                    "original_density": pt_result["density"],
                    "original_enthalpy": pt_result["enthalpy"],
                    "fluid_index": fluid_index,
                    "fluid_desc": fluid_desc
                }
                
                # Add all additional properties for comparison
                for prop in ["internal_energy", "Cv", "Cp", "sound_speed", 
                            "compressibility_factor", "viscosity", "thermal_conductivity"]:
                    if prop in result and prop in pt_result:
                        ts_result[prop] = result[prop]["value"]
                        ts_result[f"original_{prop}"] = pt_result[prop]
                
                ts_results.append(ts_result)
                print(f"TS-flash completed for fluid: {fluid_desc}, T={pt_result['temperature']}°C, S={pt_result['entropy']:.2f} J/(mol·K)")
                
            except Exception as e:
                print(f"Error in TS-flash calculation for fluid: {fluid_desc}, T={pt_result['temperature']}°C, S={pt_result['entropy']:.2f} J/(mol·K): {str(e)}")
                continue
        
        # Brief pause between batches
        if batch_idx < len(ts_batches):
            time.sleep(0.5)
    
    # Part 4: Compare results and calculate differences
    print("\nComparing PT-flash, PH-flash, and TS-flash results:")
    print("=" * 80)
    
    # 4.1: First comparison - PT vs PH
    print("\nComparison 1: PT-flash vs PH-flash")
    pt_ph_comparison_results = []
    
    # Group results by fluid for better analysis
    fluid_pt_ph_results = {}
    fluid_pt_ts_results = {}
    
    # Process PT vs PH comparisons
    for ph_result in ph_results:
        fluid_index = ph_result["fluid_index"]
        fluid_desc = ph_result["fluid_desc"]
        
        # Initialize the fluid entry if it doesn't exist
        if fluid_index not in fluid_pt_ph_results:
            fluid_pt_ph_results[fluid_index] = []
        
        # Initialize comparison dictionary with basic properties
        comparison = {
            "pressure": ph_result["pressure"],
            "original_T": ph_result["original_temperature"],
            "calculated_T": ph_result["temperature"],
            "phase": ph_result["phase"],
            "vapor_fraction": ph_result["vapor_fraction"],
            "fluid_index": fluid_index,
            "fluid_desc": fluid_desc
        }
        
        # Process each property with proper error handling
        properties_to_compare = [
            {"name": "temperature", "short": "T", "original_key": "original_temperature", "calculated_key": "temperature", "abs_scale": 1.0, "use_kelvin": True},
            {"name": "density", "short": "D", "original_key": "original_density", "calculated_key": "density", "abs_scale": 1.0, "use_kelvin": False},
            {"name": "entropy", "short": "S", "original_key": "original_entropy", "calculated_key": "entropy", "abs_scale": 0.001, "use_kelvin": False},
            {"name": "internal_energy", "short": "U", "original_key": "original_internal_energy", "calculated_key": "internal_energy", "abs_scale": 0.001, "use_kelvin": False},
            {"name": "Cv", "short": "Cv", "original_key": "original_Cv", "calculated_key": "Cv", "abs_scale": 0.001, "use_kelvin": False},
            {"name": "Cp", "short": "Cp", "original_key": "original_Cp", "calculated_key": "Cp", "abs_scale": 0.001, "use_kelvin": False},
            {"name": "sound_speed", "short": "W", "original_key": "original_sound_speed", "calculated_key": "sound_speed", "abs_scale": 0.1, "use_kelvin": False},
            {"name": "compressibility_factor", "short": "Z", "original_key": "original_compressibility_factor", "calculated_key": "compressibility_factor", "abs_scale": 0.001, "use_kelvin": False},
            {"name": "viscosity", "short": "Visc", "original_key": "original_viscosity", "calculated_key": "viscosity", "abs_scale": 0.01, "use_kelvin": False},
            {"name": "thermal_conductivity", "short": "TC", "original_key": "original_thermal_conductivity", "calculated_key": "thermal_conductivity", "abs_scale": 0.001, "use_kelvin": False}
        ]
        
        # Calculate differences for each property
        for prop in properties_to_compare:
            if prop["original_key"] in ph_result and prop["calculated_key"] in ph_result:
                original_val = ph_result[prop["original_key"]]
                calculated_val = ph_result[prop["calculated_key"]]
                
                # Store original and calculated values
                comparison[f"original_{prop['short']}"] = original_val
                comparison[f"calculated_{prop['short']}"] = calculated_val
                
                # Calculate absolute difference (scaled for better readability)
                diff_abs = (calculated_val - original_val) * prop["abs_scale"]
                comparison[f"{prop['short']}_diff_abs"] = diff_abs
                
                # Calculate relative difference (special handling for temperature)
                if prop["use_kelvin"]:
                    # For temperature, convert to Kelvin for relative comparison
                    diff_rel = diff_abs / ((original_val + 273.15) * prop["abs_scale"]) * 100
                else:
                    # Prevent division by zero
                    if original_val != 0:
                        diff_rel = diff_abs / (original_val * prop["abs_scale"]) * 100
                    else:
                        diff_rel = np.nan
                        
                comparison[f"{prop['short']}_diff_rel"] = diff_rel
        
        fluid_pt_ph_results[fluid_index].append(comparison)
        pt_ph_comparison_results.append(comparison)
    
    # 4.2: Second comparison - PT vs TS
    print("\nComparison 2: PT-flash vs TS-flash")
    pt_ts_comparison_results = []
    
    # Process PT vs TS comparisons
    for ts_result in ts_results:
        fluid_index = ts_result["fluid_index"]
        fluid_desc = ts_result["fluid_desc"]
        
        # Initialize the fluid entry if it doesn't exist
        if fluid_index not in fluid_pt_ts_results:
            fluid_pt_ts_results[fluid_index] = []
        
        # Initialize comparison dictionary with basic properties
        comparison = {
            "temperature": ts_result["temperature"],
            "original_P": ts_result["original_pressure"],
            "calculated_P": ts_result["pressure"],
            "phase": ts_result["phase"],
            "vapor_fraction": ts_result["vapor_fraction"],
            "fluid_index": fluid_index,
            "fluid_desc": fluid_desc
        }
        
        # Process each property with proper error handling
        properties_to_compare = [
            {"name": "pressure", "short": "P", "original_key": "original_pressure", "calculated_key": "pressure", "abs_scale": 1.0, "use_kelvin": False},
            {"name": "density", "short": "D", "original_key": "original_density", "calculated_key": "density", "abs_scale": 1.0, "use_kelvin": False},
            {"name": "enthalpy", "short": "H", "original_key": "original_enthalpy", "calculated_key": "enthalpy", "abs_scale": 0.001, "use_kelvin": False},
            {"name": "internal_energy", "short": "U", "original_key": "original_internal_energy", "calculated_key": "internal_energy", "abs_scale": 0.001, "use_kelvin": False},
            {"name": "Cv", "short": "Cv", "original_key": "original_Cv", "calculated_key": "Cv", "abs_scale": 0.001, "use_kelvin": False},
            {"name": "Cp", "short": "Cp", "original_key": "original_Cp", "calculated_key": "Cp", "abs_scale": 0.001, "use_kelvin": False},
            {"name": "sound_speed", "short": "W", "original_key": "original_sound_speed", "calculated_key": "sound_speed", "abs_scale": 0.1, "use_kelvin": False},
            {"name": "compressibility_factor", "short": "Z", "original_key": "original_compressibility_factor", "calculated_key": "compressibility_factor", "abs_scale": 0.001, "use_kelvin": False},
            {"name": "viscosity", "short": "Visc", "original_key": "original_viscosity", "calculated_key": "viscosity", "abs_scale": 0.01, "use_kelvin": False},
            {"name": "thermal_conductivity", "short": "TC", "original_key": "original_thermal_conductivity", "calculated_key": "thermal_conductivity", "abs_scale": 0.001, "use_kelvin": False}
        ]
        
        # Calculate differences for each property
        for prop in properties_to_compare:
            if prop["original_key"] in ts_result and prop["calculated_key"] in ts_result:
                original_val = ts_result[prop["original_key"]]
                calculated_val = ts_result[prop["calculated_key"]]
                
                # Store original and calculated values
                comparison[f"original_{prop['short']}"] = original_val
                comparison[f"calculated_{prop['short']}"] = calculated_val
                
                # Calculate absolute difference (scaled for better readability)
                diff_abs = (calculated_val - original_val) * prop["abs_scale"]
                comparison[f"{prop['short']}_diff_abs"] = diff_abs
                
                # Calculate relative difference
                if original_val != 0:
                    diff_rel = diff_abs / (original_val * prop["abs_scale"]) * 100
                else:
                    diff_rel = np.nan
                        
                comparison[f"{prop['short']}_diff_rel"] = diff_rel
        
        fluid_pt_ts_results[fluid_index].append(comparison)
        pt_ts_comparison_results.append(comparison)
    
    # 4.3: Create DataFrames for better display
    df_pt_ph = pd.DataFrame(pt_ph_comparison_results)
    df_pt_ts = pd.DataFrame(pt_ts_comparison_results)
    
    # Identify all property columns for rounding and statistics
    property_columns = {}
    for col in df_pt_ph.columns:
        if col.endswith('_diff_abs') or col.endswith('_diff_rel'):
            property_columns[col] = 6
        elif col.startswith('original_') or col.startswith('calculated_'):
            property_columns[col] = 4
    
    # Round values for better readability
    df_pt_ph = df_pt_ph.round(property_columns)
    df_pt_ts = df_pt_ts.round(property_columns)
    
    # 5: Calculate summary statistics for each fluid
    print("\nSummary Statistics for PT-flash vs PH-flash by Fluid Type:")
    property_shorts_pt_ph = ["T", "D", "S", "U", "Cv", "Cp", "W", "Z", "Visc", "TC"]
    property_names_pt_ph = [
        "Temperature", "Density", "Entropy", "Internal Energy", 
        "Cv", "Cp", "Sound Speed", "Compressibility", 
        "Viscosity", "Thermal Conductivity"
    ]
    property_units_pt_ph = [
        "°C", "mol/L", "J/(mol·K)", "J/mol", 
        "J/(mol·K)", "J/(mol·K)", "m/s", "-", 
        "μPa·s", "W/(m·K)"
    ]
    
    # Table for PT vs PH summary statistics by fluid
    summary_headers = ["Fluid Type", "Property", "Unit", "Mean Abs Diff", "Max Abs Diff", "Mean Rel Diff", "Max Rel Diff"]
    pt_ph_fluid_summary = []
    
    for fluid_index in sorted(fluid_pt_ph_results.keys()):
        fluid_desc = composition_descriptions[fluid_index]
        fluid_data = pd.DataFrame(fluid_pt_ph_results[fluid_index])
        
        for short, name, unit in zip(property_shorts_pt_ph, property_names_pt_ph, property_units_pt_ph):
            abs_col = f"{short}_diff_abs"
            rel_col = f"{short}_diff_rel"
            
            if abs_col in fluid_data.columns and rel_col in fluid_data.columns:
                # Calculate statistics
                abs_mean = fluid_data[abs_col].abs().mean()
                abs_max = fluid_data[abs_col].abs().max()
                rel_mean = fluid_data[rel_col].abs().mean()
                rel_max = fluid_data[rel_col].abs().max()
                
                # Add to summary table
                pt_ph_fluid_summary.append([
                    fluid_desc,
                    name, 
                    unit, 
                    f"{abs_mean:.6f}", 
                    f"{abs_max:.6f}", 
                    f"{rel_mean:.4f}%", 
                    f"{rel_max:.4f}%"
                ])
    
    # Display the PT vs PH summary statistics table by fluid
    print(tabulate(pt_ph_fluid_summary, headers=summary_headers, tablefmt="grid"))
    
    print("\nSummary Statistics for PT-flash vs TS-flash by Fluid Type:")
    property_shorts_pt_ts = ["P", "D", "H", "U", "Cv", "Cp", "W", "Z", "Visc", "TC"]
    property_names_pt_ts = [
        "Pressure", "Density", "Enthalpy", "Internal Energy", 
        "Cv", "Cp", "Sound Speed", "Compressibility", 
        "Viscosity", "Thermal Conductivity"
    ]
    property_units_pt_ts = [
        "bar", "mol/L", "J/mol", "J/mol", 
        "J/(mol·K)", "J/(mol·K)", "m/s", "-", 
        "μPa·s", "W/(m·K)"
    ]
    
    # Table for PT vs TS summary statistics by fluid
    pt_ts_fluid_summary = []
    
    for fluid_index in sorted(fluid_pt_ts_results.keys()):
        fluid_desc = composition_descriptions[fluid_index]
        fluid_data = pd.DataFrame(fluid_pt_ts_results[fluid_index])
        
        for short, name, unit in zip(property_shorts_pt_ts, property_names_pt_ts, property_units_pt_ts):
            abs_col = f"{short}_diff_abs"
            rel_col = f"{short}_diff_rel"
            
            if abs_col in fluid_data.columns and rel_col in fluid_data.columns:
                # Calculate statistics
                abs_mean = fluid_data[abs_col].abs().mean()
                abs_max = fluid_data[abs_col].abs().max()
                rel_mean = fluid_data[rel_col].abs().mean()
                rel_max = fluid_data[rel_col].abs().max()
                
                # Add to summary table
                pt_ts_fluid_summary.append([
                    fluid_desc,
                    name, 
                    unit, 
                    f"{abs_mean:.6f}", 
                    f"{abs_max:.6f}", 
                    f"{rel_mean:.4f}%", 
                    f"{rel_max:.4f}%"
                ])
    
    # Display the PT vs TS summary statistics table by fluid
    print(tabulate(pt_ts_fluid_summary, headers=summary_headers, tablefmt="grid"))
    
    # 6: Calculate overall summary statistics
    print("\nOverall Summary Statistics for PT-flash vs PH-flash:")
    
    # Table for PT vs PH overall summary statistics
    summary_table_pt_ph = []
    
    for short, name, unit in zip(property_shorts_pt_ph, property_names_pt_ph, property_units_pt_ph):
        abs_col = f"{short}_diff_abs"
        rel_col = f"{short}_diff_rel"
        
        if abs_col in df_pt_ph.columns and rel_col in df_pt_ph.columns:
            # Calculate statistics
            abs_mean = df_pt_ph[abs_col].abs().mean()
            abs_max = df_pt_ph[abs_col].abs().max()
            rel_mean = df_pt_ph[rel_col].abs().mean()
            rel_max = df_pt_ph[rel_col].abs().max()
            
            # Add to summary table
            summary_table_pt_ph.append([
                name, unit, f"{abs_mean:.6f}", f"{abs_max:.6f}", 
                f"{rel_mean:.4f}%", f"{rel_max:.4f}%"
            ])
    
    # Display the PT vs PH overall summary statistics table
    summary_headers_overall = ["Property", "Unit", "Mean Abs Diff", "Max Abs Diff", "Mean Rel Diff", "Max Rel Diff"]
    print(tabulate(summary_table_pt_ph, headers=summary_headers_overall, tablefmt="grid"))
    
    print("\nOverall Summary Statistics for PT-flash vs TS-flash:")
    
    # Table for PT vs TS overall summary statistics
    summary_table_pt_ts = []
    
    for short, name, unit in zip(property_shorts_pt_ts, property_names_pt_ts, property_units_pt_ts):
        abs_col = f"{short}_diff_abs"
        rel_col = f"{short}_diff_rel"
        
        if abs_col in df_pt_ts.columns and rel_col in df_pt_ts.columns:
            # Calculate statistics
            abs_mean = df_pt_ts[abs_col].abs().mean()
            abs_max = df_pt_ts[abs_col].abs().max()
            rel_mean = df_pt_ts[rel_col].abs().mean()
            rel_max = df_pt_ts[rel_col].abs().max()
            
            # Add to summary table
            summary_table_pt_ts.append([
                name, unit, f"{abs_mean:.6f}", f"{abs_max:.6f}", 
                f"{rel_mean:.4f}%", f"{rel_max:.4f}%"
            ])
    
    # Display the PT vs TS overall summary statistics table
    print(tabulate(summary_table_pt_ts, headers=summary_headers_overall, tablefmt="grid"))
    
    # 7: Display key comparison details
    # Display the temperature and pressure comparison as main tables (most important properties)
    print("\nDetailed PT-flash vs PH-flash Comparison Sample (Temperature and Density):")
    headers_pt_ph = [
        "Fluid", "P (bar)", "Original T (°C)", "Calc T (°C)", "T diff", "T diff %", 
        "Original D (mol/L)", "Calc D (mol/L)", "D diff", "D diff %", "Phase"
    ]
    
    # Use only columns that definitely exist
    display_columns_pt_ph = ['fluid_desc', 'pressure']
    for col in ['original_T', 'calculated_T', 'T_diff_abs', 'T_diff_rel',
               'original_D', 'calculated_D', 'D_diff_abs', 'D_diff_rel', 'phase']:
        if col in df_pt_ph.columns:
            display_columns_pt_ph.append(col)
    
    # Show a sample of results (first few rows from each fluid)
    sample_rows = []
    for fluid_index in sorted(fluid_pt_ph_results.keys()):
        if fluid_pt_ph_results[fluid_index]:
            fluid_df = pd.DataFrame(fluid_pt_ph_results[fluid_index])
            if len(display_columns_pt_ph) <= len(fluid_df.columns):
                sample_rows.extend(fluid_df[display_columns_pt_ph].head(2).values.tolist())
    
    print(tabulate(sample_rows, headers=headers_pt_ph[:len(display_columns_pt_ph)], tablefmt="grid"))
    
    print("\nDetailed PT-flash vs TS-flash Comparison Sample (Pressure and Density):")
    headers_pt_ts = [
        "Fluid", "T (°C)", "Original P (bar)", "Calc P (bar)", "P diff", "P diff %", 
        "Original D (mol/L)", "Calc D (mol/L)", "D diff", "D diff %", "Phase"
    ]
    
    # Use only columns that definitely exist
    display_columns_pt_ts = ['fluid_desc', 'temperature']
    for col in ['original_P', 'calculated_P', 'P_diff_abs', 'P_diff_rel',
               'original_D', 'calculated_D', 'D_diff_abs', 'D_diff_rel', 'phase']:
        if col in df_pt_ts.columns:
            display_columns_pt_ts.append(col)
    
    # Show a sample of results (first few rows from each fluid)
    sample_rows = []
    for fluid_index in sorted(fluid_pt_ts_results.keys()):
        if fluid_pt_ts_results[fluid_index]:
            fluid_df = pd.DataFrame(fluid_pt_ts_results[fluid_index])
            if len(display_columns_pt_ts) <= len(fluid_df.columns):
                sample_rows.extend(fluid_df[display_columns_pt_ts].head(2).values.tolist())
    
    print(tabulate(sample_rows, headers=headers_pt_ts[:len(display_columns_pt_ts)], tablefmt="grid"))
    
    # 8: Calculate overall consistency scores by fluid
    print("\nConsistency Scores by Fluid:")
    consistency_table = []
    
    for fluid_index in sorted(fluid_pt_ph_results.keys()):
        if fluid_index in fluid_pt_ts_results:
            fluid_desc = composition_descriptions[fluid_index]
            fluid_pt_ph_df = pd.DataFrame(fluid_pt_ph_results[fluid_index])
            fluid_pt_ts_df = pd.DataFrame(fluid_pt_ts_results[fluid_index])
            
            # PT vs PH temperature consistency
            t_diff_rel_mean = np.nan
            d_diff_rel_mean = np.nan
            if 'T_diff_rel' in fluid_pt_ph_df.columns:
                t_diff_rel_mean = fluid_pt_ph_df['T_diff_rel'].abs().mean()
            if 'D_diff_rel' in fluid_pt_ph_df.columns:
                d_diff_rel_mean = fluid_pt_ph_df['D_diff_rel'].abs().mean()
                
            # PT vs TS pressure consistency
            p_diff_rel_mean = np.nan
            if 'P_diff_rel' in fluid_pt_ts_df.columns:
                p_diff_rel_mean = fluid_pt_ts_df['P_diff_rel'].abs().mean()
                
            # Determine consistency level
            pt_ph_status = "Unknown"
            if not np.isnan(t_diff_rel_mean) and not np.isnan(d_diff_rel_mean):
                if t_diff_rel_mean < 0.5 and d_diff_rel_mean < 0.5:
                    pt_ph_status = "High"
                elif t_diff_rel_mean < 2.0 and d_diff_rel_mean < 2.0:
                    pt_ph_status = "Medium"
                else:
                    pt_ph_status = "Low"
                    
            pt_ts_status = "Unknown"
            if not np.isnan(p_diff_rel_mean) and not np.isnan(d_diff_rel_mean):
                if p_diff_rel_mean < 0.5 and d_diff_rel_mean < 0.5:
                    pt_ts_status = "High"
                elif p_diff_rel_mean < 2.0 and d_diff_rel_mean < 2.0:
                    pt_ts_status = "Medium"
                else:
                    pt_ts_status = "Low"
                    
            # Overall consistency
            overall_status = "Unknown"
            if pt_ph_status != "Unknown" and pt_ts_status != "Unknown":
                if pt_ph_status == "High" and pt_ts_status == "High":
                    overall_status = "High"
                elif pt_ph_status == "Low" or pt_ts_status == "Low":
                    overall_status = "Low"
                else:
                    overall_status = "Medium"
                    
            consistency_table.append([
                fluid_desc,
                f"{t_diff_rel_mean:.2f}%" if not np.isnan(t_diff_rel_mean) else "N/A",
                f"{d_diff_rel_mean:.2f}%" if not np.isnan(d_diff_rel_mean) else "N/A",
                f"{p_diff_rel_mean:.2f}%" if not np.isnan(p_diff_rel_mean) else "N/A",
                pt_ph_status,
                pt_ts_status,
                overall_status
            ])
    
    consistency_headers = ["Fluid", "Avg T Diff", "Avg D Diff", "Avg P Diff", "PT-PH Consistency", "PT-TS Consistency", "Overall"]
    print(tabulate(consistency_table, headers=consistency_headers, tablefmt="grid"))
    
    # 9: Overall evaluation
    print("\nOverall Sanity Check Results:")
    
    # Calculate overall scores across all fluids
    overall_t_diff = df_pt_ph['T_diff_rel'].abs().mean() if 'T_diff_rel' in df_pt_ph.columns else np.nan
    overall_d_diff_ph = df_pt_ph['D_diff_rel'].abs().mean() if 'D_diff_rel' in df_pt_ph.columns else np.nan
    overall_p_diff = df_pt_ts['P_diff_rel'].abs().mean() if 'P_diff_rel' in df_pt_ts.columns else np.nan
    overall_d_diff_ts = df_pt_ts['D_diff_rel'].abs().mean() if 'D_diff_rel' in df_pt_ts.columns else np.nan
    
    # PT vs PH evaluation
    if not np.isnan(overall_t_diff) and not np.isnan(overall_d_diff_ph):
        if overall_t_diff < 0.5 and overall_d_diff_ph < 0.5:
            pt_ph_result = "PASSED: PT-flash and PH-flash results are highly consistent."
        elif overall_t_diff < 2.0 and overall_d_diff_ph < 2.0:
            pt_ph_result = "PARTIALLY PASSED: Some discrepancies exist but are within reasonable limits."
        else:
            pt_ph_result = "FAILED: Significant discrepancies between PT-flash and PH-flash results."
    else:
        pt_ph_result = "UNABLE TO EVALUATE: Missing or invalid comparison data."
    
    # PT vs TS evaluation
    if not np.isnan(overall_p_diff) and not np.isnan(overall_d_diff_ts):
        if overall_p_diff < 0.5 and overall_d_diff_ts < 0.5:
            pt_ts_result = "PASSED: PT-flash and TS-flash results are highly consistent."
        elif overall_p_diff < 2.0 and overall_d_diff_ts < 2.0:
            pt_ts_result = "PARTIALLY PASSED: Some discrepancies exist but are within reasonable limits."
        else:
            pt_ts_result = "FAILED: Significant discrepancies between PT-flash and TS-flash results."
    else:
        pt_ts_result = "UNABLE TO EVALUATE: Missing or invalid comparison data."
    
    # Show overall results
    print(f"\nPT-flash vs PH-flash: {pt_ph_result}")
    print(f"PT-flash vs TS-flash: {pt_ts_result}")
    
    # Overall cross-consistency result
    if pt_ph_result.startswith("PASSED") and pt_ts_result.startswith("PASSED"):
        print("\nOVERALL SANITY CHECK: PASSED")
        print("All three calculation methods (PT, PH, TS) are consistently producing the same thermodynamic properties.")
    elif pt_ph_result.startswith("PARTIALLY") and pt_ts_result.startswith("PARTIALLY"):
        print("\nOVERALL SANITY CHECK: PARTIALLY PASSED")
        print("The three calculation methods show moderate consistency with acceptable discrepancies.")
    elif "FAILED" in pt_ph_result or "FAILED" in pt_ts_result:
        print("\nOVERALL SANITY CHECK: FAILED")
        print("Significant discrepancies exist between the different calculation methods.")
    else:
        print("\nOVERALL SANITY CHECK: INCONCLUSIVE")
        print("Could not properly evaluate consistency across all three calculation methods.")
    
    # 10: Check for any specific fluid or property issues
    print("\nFluid-specific observations:")
    
    # Look for problem fluids
    problem_fluids = []
    for row in consistency_table:
        if row[6] == "Low":  # Overall consistency is low
            problem_fluids.append(row[0])  # Add fluid name
    
    if problem_fluids:
        print(f"- Warning: The following fluids show poor consistency across calculation methods: {', '.join(problem_fluids)}")
    
    print("\nProperty-specific observations:")
    
    # PT vs PH property issues
    for short, name in zip(property_shorts_pt_ph, property_names_pt_ph):
        rel_col = f"{short}_diff_rel"
        if rel_col in df_pt_ph.columns and not df_pt_ph[rel_col].isnull().all():
            mean_diff = df_pt_ph[rel_col].abs().mean()
            
            if mean_diff > 5.0:
                print(f"- Warning: PT vs PH {name} shows large discrepancies (mean {mean_diff:.2f}%)")
            elif mean_diff > 2.0:
                print(f"- Note: PT vs PH {name} shows moderate discrepancies (mean {mean_diff:.2f}%)")
    
    # PT vs TS property issues
    for short, name in zip(property_shorts_pt_ts, property_names_pt_ts):
        rel_col = f"{short}_diff_rel"
        if rel_col in df_pt_ts.columns and not df_pt_ts[rel_col].isnull().all():
            mean_diff = df_pt_ts[rel_col].abs().mean()
            
            if mean_diff > 5.0:
                print(f"- Warning: PT vs TS {name} shows large discrepancies (mean {mean_diff:.2f}%)")
            elif mean_diff > 2.0:
                print(f"- Note: PT vs TS {name} shows moderate discrepancies (mean {mean_diff:.2f}%)")
    
    print("\nPossible reasons for discrepancies:")
    print("1. Numerical precision in the solvers")
    print("2. Iteration tolerance settings in REFPROP")
    print("3. Different solution paths in PT vs PH vs TS flash calculations")
    print("4. Properties near phase boundaries or critical region")
    print("5. Implementation differences between flash algorithms")
    print("6. Thermodynamic consistency of the underlying equation of state")
    print("7. Specific fluid behavior in certain temperature/pressure regions")
    
    # 11: Display detailed property comparison for a specific test point
    if len(df_pt_ph) > 0 and len(df_pt_ts) > 0:
        print("\nDetailed comparison for first test point:")
        print("\nPT-flash vs PH-flash:")
        first_point_pt_ph = df_pt_ph.iloc[0]
        detailed_comparison_pt_ph = []
        
        for short, name, unit in zip(property_shorts_pt_ph, property_names_pt_ph, property_units_pt_ph):
            orig_col = f"original_{short}"
            calc_col = f"calculated_{short}"
            abs_col = f"{short}_diff_abs"
            rel_col = f"{short}_diff_rel"
            
            if orig_col in first_point_pt_ph and calc_col in first_point_pt_ph:
                detailed_comparison_pt_ph.append([
                    name,
                    unit,
                    f"{first_point_pt_ph[orig_col]:.6g}",
                    f"{first_point_pt_ph[calc_col]:.6g}",
                    f"{first_point_pt_ph.get(abs_col, 'N/A'):.6g}" if abs_col in first_point_pt_ph else "N/A",
                    f"{first_point_pt_ph.get(rel_col, 'N/A'):.4g}%" if rel_col in first_point_pt_ph else "N/A"
                ])
        
        detail_headers = ["Property", "Unit", "PT Value", "PH Value", "Abs Diff", "Rel Diff"]
        print(tabulate(detailed_comparison_pt_ph, headers=detail_headers, tablefmt="grid"))
        
        print("\nPT-flash vs TS-flash:")
        first_point_pt_ts = df_pt_ts.iloc[0]
        detailed_comparison_pt_ts = []
        
        for short, name, unit in zip(property_shorts_pt_ts, property_names_pt_ts, property_units_pt_ts):
            orig_col = f"original_{short}"
            calc_col = f"calculated_{short}"
            abs_col = f"{short}_diff_abs"
            rel_col = f"{short}_diff_rel"
            
            if orig_col in first_point_pt_ts and calc_col in first_point_pt_ts:
                detailed_comparison_pt_ts.append([
                    name,
                    unit,
                    f"{first_point_pt_ts[orig_col]:.6g}",
                    f"{first_point_pt_ts[calc_col]:.6g}",
                    f"{first_point_pt_ts.get(abs_col, 'N/A'):.6g}" if abs_col in first_point_pt_ts else "N/A",
                    f"{first_point_pt_ts.get(rel_col, 'N/A'):.4g}%" if rel_col in first_point_pt_ts else "N/A"
                ])
        
        detail_headers = ["Property", "Unit", "PT Value", "TS Value", "Abs Diff", "Rel Diff"]
        print(tabulate(detailed_comparison_pt_ts, headers=detail_headers, tablefmt="grid"))
    
    # Return all results for further analysis if needed
    return {
        'pt_ph_comparison': df_pt_ph,
        'pt_ts_comparison': df_pt_ts,
        'fluid_results': {
            'pt_ph': fluid_pt_ph_results,
            'pt_ts': fluid_pt_ts_results
        }
    }