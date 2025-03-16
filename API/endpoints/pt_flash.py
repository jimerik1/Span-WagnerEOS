from flask import request, jsonify, Response
import numpy as np
import sys
import traceback
from typing import List, Dict, Any

from API.endpoints import pt_flash_bp
from API.refprop_setup import RP
from API.unit_converter import UnitConverter
from API.utils.helpers import get_phase
from API.utils.grid_generator import generate_grid, get_phase_boundaries_pt

def validate_composition(composition: List[Dict[str, Any]]) -> bool:
    """Validate composition data"""
    total = sum(comp['fraction'] for comp in composition)
    return abs(total - 1.0) < 1e-6

def setup_mixture(composition: List[Dict[str, Any]]) -> List[float]:
    """Setup REFPROP mixture"""
    fluid_string = '|'.join(f"{comp['fluid']}.FLD" for comp in composition)
    z = [comp['fraction'] for comp in composition] + [0] * (20 - len(composition))
    
    ierr, herr = RP.SETUPdll(len(composition), fluid_string, 'HMX.BNC', 'DEF')
    if ierr > 0:
        raise ValueError(f"Error setting up mixture: {herr}")
    return z

def calculate_properties(z: List[float], T: float, P: float, units_system: str = 'SI') -> Dict[str, Any]:
    """
    Calculate fluid properties at given temperature and pressure with specified unit system.
    
    Args:
        z: Composition array
        T: Temperature in K
        P: Pressure in bar
        units_system: Unit system to use ('SI' or 'CGS')
    
    Returns:
        Dictionary of calculated properties with values and units
    """
    # Initialize unit converter
    converter = UnitConverter()
    
    # Get molecular weight for unit conversions
    wmm = RP.WMOLdll(z)
    
    # Convert pressure to kPa for REFPROP
    P_kpa = P * 100  # bar to kPa
    
    # Get basic thermodynamic properties
    D, Dl, Dv, x, y, q, e, h, s, Cv, Cp, w, ierr, herr = RP.TPFLSHdll(T, P_kpa, z)
    if ierr > 0:
        raise ValueError(f"Error in TPFLSHdll: {herr}")
    
    # Get transport properties
    eta, tcx, ierr, herr = RP.TRNPRPdll(T, D, z)
    if ierr > 0:
        raise ValueError(f"Error in TRNPRPdll: {herr}")
        
    # Get surface tension if in two-phase region
    if 0 < q < 1:
        sigma, ierr, herr = RP.SURTENdll(T, Dl, Dv, x, y)
        surface_tension = float(sigma) if ierr == 0 else None
    else:
        surface_tension = None
        
    # Get critical properties
    Tc, Pc, Dc, ierr, herr = RP.CRITPdll(z)
    if ierr > 0:
        Tc = Pc = Dc = None
        
    # Get additional thermodynamic derivatives
    dPdD, dPdT, d2PdD2, d2PdT2, d2PdTD, dDdP, dDdT, d2DdP2, d2DdT2, d2DdPT, \
    dTdP, dTdD, d2TdP2, d2TdD2, d2TdPD = RP.DERVPVTdll(T, D, z)
    
    # Calculate compressibility factor
    Z = P_kpa / (D * 8.31446261815324 * T)
    
    # Get molecular weight for conversions
    wmm_kg = wmm / 1000  # Convert g/mol to kg/mol

    # Build raw properties dictionary
    raw_properties = {
        'density': D,
        'liquid_density': Dl,
        'vapor_density': Dv,
        'vapor_fraction': q,
        'internal_energy': e,
        'enthalpy': h,
        'entropy': s,
        'cv': Cv,
        'cp': Cp,
        'sound_speed': w,
        'viscosity': eta,
        'thermal_conductivity': tcx,
        'surface_tension': surface_tension,
        'critical_temperature': Tc,
        'critical_pressure': Pc / 100,  # Convert from kPa to bar
        'critical_density': Dc,
        'compressibility_factor': Z,
        'isothermal_compressibility': -1/D * dDdP,
        'volume_expansivity': 1/D * dDdT,
        'dp_dt_saturation': dPdT,
        'joule_thomson_coefficient': (T*dDdT/dDdP - 1)/(Cp * 100),  # Convert to K/bar
        'kinematic_viscosity': (eta * 1e-6) / (D * wmm / 1000) * 10000,
        'thermal_diffusivity': tcx / (D * Cp) * 10000,  # Convert to cm²/s
        'prandtl_number': (Cp / wmm_kg) * (eta * 1e-6) / tcx,
        'temperature': T - 273.15,  # Convert to Celsius
        'pressure': P,
        'x': list(x[:len(z)]),  # Liquid composition
        'y': list(y[:len(z)]),  # Vapor composition
        'dDdP': dDdP,          # Add pressure derivative of density
        'dDdT': dDdT           # Add temperature derivative of density
    }
    
    # Convert properties to requested unit system
    properties = {}
    for prop_id, value in raw_properties.items():
        if value is not None:  # Skip undefined properties
            try:
                if prop_id in ['x', 'y']:
                    # Composition vectors
                    properties[prop_id] = {'value': value, 'unit': 'mole fraction'}
                else:
                    properties[prop_id] = converter.convert_property(
                        prop_id, float(value), wmm, 'SI', units_system
                    )
            except Exception as e:
                print(f"Warning: Could not convert property {prop_id}: {str(e)}")
                properties[prop_id] = {'value': float(value), 'unit': 'unknown'}
    
    # Add phase information
    properties['phase'] = {
        'value': get_phase(q),
        'unit': None
    }
    
    return properties

@pt_flash_bp.route('/pt_flash', methods=['POST'])
def pt_flash():
    try:
        data = request.get_json(force=True)
        
        # Validate the request structure
        required_fields = ['composition', 'variables']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing field: {field}'}), 400
                
        # Check if required variables exist
        variables = data.get('variables', {})
        if 'pressure' not in variables or 'temperature' not in variables:
            return jsonify({'error': 'Missing pressure or temperature variables'}), 400

        # Extract calculation settings
        calculation = data.get('calculation', {})
        properties = calculation.get('properties', [])
        units_system = calculation.get('units_system', 'SI')  # Default to SI
        response_format = calculation.get('response_format', 'json')  # Default to JSON
        
        # Extract grid_type parameter and related options
        grid_type = calculation.get('grid_type', 'equidistant')  # Default to equidistant grid
        enhancement_factor = calculation.get('enhancement_factor', 5.0)  
        boundary_zone_width = calculation.get('boundary_zone_width', None)  
        
        if not properties:
            return jsonify({'error': 'No properties specified for calculation'}), 400

        # Validate composition
        if not validate_composition(data['composition']):
            return jsonify({'error': 'Invalid composition - fractions must sum to 1'}), 400

        # Setup mixture
        z = setup_mixture(data['composition'])
        
        # Get molecular weight for unit conversions
        wmm = RP.WMOLdll(z)

        # Extract range and resolution parameters with robust error handling
        try:
            pressure_range = variables['pressure'].get('range', {})
            temperature_range = variables['temperature'].get('range', {})
            
            # Ensure all necessary values exist with defaults if not
            p_from = float(pressure_range.get('from', 1.0))
            p_to = float(pressure_range.get('to', 100.0))
            t_from = float(temperature_range.get('from', 0.0))
            t_to = float(temperature_range.get('to', 100.0))
            
            pressure_resolution = float(variables['pressure'].get('resolution', 10.0))
            temperature_resolution = float(variables['temperature'].get('resolution', 5.0))
            
            # Ensure to > from
            if p_to <= p_from:
                p_to = p_from + pressure_resolution
            if t_to <= t_from:
                t_to = t_from + temperature_resolution
                
            # Update the ranges for later use
            pressure_range = {'from': p_from, 'to': p_to}
            temperature_range = {'from': t_from, 'to': t_to}
            
        except (ValueError, TypeError) as ve:
            return jsonify({'error': f'Invalid range or resolution parameters: {str(ve)}'}), 400

        # Debug log
        print(f"Calculating PT flash for temperature range: {temperature_range['from']} to {temperature_range['to']} °C, "
              f"pressure range: {pressure_range['from']} to {pressure_range['to']} bar, grid_type: {grid_type}")

        # Generate grids based on grid_type
        if grid_type.lower() != 'equidistant':
            # If we're using an adaptive grid, determine phase boundaries first
            if grid_type.lower() == 'adaptive':
                try:
                    # Get phase boundaries in P-T space
                    t_boundaries, p_boundaries = get_phase_boundaries_pt(
                        RP, z, temperature_range, pressure_range
                    )
                    
                    print(f"Identified phase boundaries: {len(t_boundaries)} temperature points, "
                          f"{len(p_boundaries)} pressure points")
                except Exception as e:
                    print(f"Error determining phase boundaries: {e}")
                    t_boundaries, p_boundaries = [], []
            else:
                t_boundaries, p_boundaries = [], []
            
            # Generate grids using the utility function
            P_range = generate_grid(
                p_from, p_to, pressure_resolution, 
                grid_type, p_boundaries, 
                enhancement_factor, boundary_zone_width
            )
            
            # For temperature, we generate grid in °C but need to convert to K for calculations
            T_range_C = generate_grid(
                t_from, t_to, temperature_resolution,
                grid_type, t_boundaries,
                enhancement_factor, boundary_zone_width
            )
            T_range = T_range_C + 273.15  # Convert to Kelvin
            
            # Debug info about the grid
            print(f"Generated {len(P_range)} pressure points and {len(T_range)} temperature points")
            
        else:
            # Create regular (equidistant) grids as before
            P_range = np.arange(
                p_from,
                p_to + pressure_resolution,
                pressure_resolution
            )
            
            T_range = np.arange(
                t_from + 273.15,  # Convert from °C to K
                t_to + 273.15 + temperature_resolution,
                temperature_resolution
            )

        # Calculate properties
        results = []
        idx = 0
        for p_idx, P in enumerate(P_range):
            for t_idx, T in enumerate(T_range):
                try:
                    props = calculate_properties(z, float(T), float(P), units_system)
                    filtered_props = {k: v for k, v in props.items() 
                                   if k in properties or k in ['temperature', 'pressure', 'phase']}
                    
                    # Add grid indices for OLGA TAB formatting
                    results.append({
                        'index': idx,
                        'p_idx': p_idx,
                        't_idx': t_idx,
                        **filtered_props
                    })
                    idx += 1
                except Exception as fe:
                    print(f"Error processing T={T-273.15}°C, P={P} bar: {fe}", file=sys.stderr)
                    continue

        # Return response in the requested format
        if response_format.lower() == 'olga_tab':
            from API.utils.olga_formatter import format_olga_tab
            try:
                # Create structured variable dictionaries for formatter
                pressure_vars = {
                    'range': {'from': P_range.min(), 'to': P_range.max()},
                    'resolution': pressure_resolution,
                    'values': P_range  # Pass the actual grid values
                }
                
                temperature_vars = {
                    'range': {'from': (T_range.min() - 273.15), 'to': (T_range.max() - 273.15)},
                    'resolution': temperature_resolution,
                    'values': T_range - 273.15  # Pass the actual grid values in °C
                }
                
                response = format_olga_tab(
                    pressure_vars,  # x-axis (pressure)
                    temperature_vars,  # y-axis (temperature)
                    results,
                    data['composition'],
                    wmm,
                    endpoint_type='pt_flash'  # Specify endpoint type for correct grid variables
                )
                return response  # Return the Response object directly
            except Exception as e:
                print(f"Error formatting OLGA TAB: {e}", file=sys.stderr)
                traceback.print_exc()
                return jsonify({'error': f'Error formatting OLGA TAB response: {str(e)}'}), 500
        else:
            # For JSON responses, include grid information
            return jsonify({
                'results': results,
                'grid_info': {
                    'type': grid_type,
                    'pressure_points': len(P_range),
                    'temperature_points': len(T_range),
                    'total_points': len(results)
                }
            })
        
    except Exception as e:
        print("Error processing request:", file=sys.stderr)
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500