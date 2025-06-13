import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from tqdm import tqdm
import os
from matplotlib.ticker import FormatStrFormatter

def preprocess_data(pnom, hour_data=True, phi=0.8, tol_speed=0.0):
    """Load and preprocess data with tolerance-adjusted power curve"""
    # Determine hub height
    height = 150 if pnom == 15 else 170
    
    # Load power curve
    power_curve = pd.read_excel(
        f"{int(pnom)}MW_power_curve.xlsx",
        decimal=',',
        usecols=['Wind Speed [m/s]', 'Power [pu]']
    ).sort_values('Wind Speed [m/s]')
    
    # Load wind data
    if hour_data:
        wind_speed = pd.read_excel(
            'buzios_metocean.xlsx',
            index_col='time',
            parse_dates=True,
            date_format='%Y/%m/%d %H:%M'
        )['wspd100'].sort_index().iloc[1:]
    else:
        wind_speed = pd.read_csv(
            f'wind_speed_1min_{int(height)}m.csv',
            index_col='datetime',
            parse_dates=True,
            date_format='%Y/%m/%d %H:%M',
            nrows=365*24*60  # 1 year
        )[f'wspd{int(height)}_phi{str(phi).replace(".","")}'].sort_index()
    
    # Preprocess wind data
    wind_speed = (wind_speed
                  .pipe(pd.to_numeric, errors='coerce')
                  .rename(f'wspd{height}')
                  .to_frame())
    
    if hour_data:
        wind_speed = wind_speed * (height/100)**0.12

    # Calculate cut-in/rated/cut-out speeds with tolerance
    power_curve_df = power_curve
    power_curve_df['next_power'] = power_curve_df['Power [pu]'].shift(-1)
    power_curve_df['previous_power'] = power_curve_df['Power [pu]'].shift(1)

    # Calculate cut-in speed with tolerance
    condition_cut_in = (
        (power_curve_df['Power [pu]'] == 0) &
        (power_curve_df['next_power'] > 0)
    )
    cut_in_speed = power_curve_df[condition_cut_in]['Wind Speed [m/s]'].max() - tol_speed

    # Calculate rated speed (unchanged)
    condition_rated = (
        (abs(power_curve_df['Power [pu]'] - 1) <= 1e-3) &
        (1 - power_curve_df['previous_power'] >= 1e-3)
    )
    rated_speed = power_curve_df[condition_rated]['Wind Speed [m/s]'].max()

    # Calculate cut-out speed with tolerance
    condition_cut_out = (
        (power_curve_df['Power [pu]'] >= 1) &
        (power_curve_df['next_power'] == 0)
    )
    cut_out_speed = power_curve_df[condition_cut_out]['Wind Speed [m/s]'].max() + tol_speed

    # Cubic fitting for wind speeds between cut-in and rated
    filtered_df = power_curve_df[
        (power_curve_df['Wind Speed [m/s]'] >= (cut_in_speed + tol_speed)) &
        (power_curve_df['Wind Speed [m/s]'] <= rated_speed)
    ]
    wind_speeds_array = filtered_df['Wind Speed [m/s]'].to_numpy()
    power_values_array = filtered_df['Power [pu]'].to_numpy()
    coeff = np.polyfit(wind_speeds_array, power_values_array, 3)

    # Define power calculation with tolerance-adjusted speeds
    def calculate_power(wind_speed):
        if wind_speed < cut_in_speed:
            return 0.0
        elif cut_in_speed <= wind_speed < rated_speed:
            return min(np.polyval(coeff, wind_speed), 1.0)
        elif rated_speed <= wind_speed <= cut_out_speed:
            return 1.0
        else:
            return 0.0
    
    # Calculate power with tolerance-adjusted curve
    wind_speed['power_pu'] = wind_speed[f'wspd{height}'].apply(calculate_power)
    return wind_speed[:-1]  # Remove last row as original

def calculate_kpi_tolerance(df, window_size, tol_speed=0.0, max_tol_points=0):
    """
    Calculate KPI with tolerance criteria:
    1. tol_speed: Wind speed tolerance (m/s)
    2. max_tol_points: Max allowed tolerance points in window
    """
    # Apply speed tolerance (using original limits for availability)
    v_cut_in = max(0, 3 - tol_speed)
    v_cut_out = 25 + tol_speed
    
    # Create availability mask with tolerance
    mask = (df.iloc[:, 0] >= v_cut_in) & (df.iloc[:, 0] <= v_cut_out)
    
    # Create tolerance band mask (points in tolerance zone)
    tol_band = ((df.iloc[:, 0] >= (3 - tol_speed)) & (df.iloc[:, 0] < 3)) | \
               ((df.iloc[:, 0] > 25) & (df.iloc[:, 0] <= (25 + tol_speed)))
    
    # Create shifted masks
    shifted = [mask.shift(-s, fill_value=False) for s in range(window_size)]
    shifted_tol = [tol_band.shift(-s, fill_value=False) for s in range(window_size)]
    
    # Combined availability (considering tolerance points)
    df['base_availability'] = pd.concat(shifted, axis=1).all(axis=1)
    tol_counts = pd.concat(shifted_tol, axis=1).sum(axis=1)
    df['tol_counts'] = tol_counts
    df['tol_counts_criteria'] = tol_counts <= max_tol_points
    df['availability'] = df['base_availability'] & df['tol_counts_criteria']
    
    # Calculate transitions
    transitions = (df['availability'] & ~df['availability'].shift(-1, fill_value=False)).sum()
    
    # Calculate available power (using tolerance-adjusted power curve)
    df['available_power'] = df['power_pu'] * df['availability']
    avg_power = df['available_power'].mean()
    
    return transitions, avg_power, df

def tolerance_sensitivity_analysis(pnom, hour_data=True, phi=0.8):
    """Run sensitivity analysis with tolerance criteria"""
    # Define maximum allowed stops
    MAX_ALLOWED_STOPS = 10000/25  # stops per year
    if hour_data:
        MAX_ALLOWED_STOPS *= 11  # 400 stops/year * 11 years
    
    # Parameter ranges
    speed_tols = np.round(np.arange(0.1, 0.51, 0.1), 1)  # 0.1 to 0.5 m/s
    point_tols = range(1, 6)  # 1 to 5 tolerance points
    window_sizes = range(1, 31)  # 1 to 30 window size
    
    # Results storage
    results = []
    
    # Main analysis loop
    for tol_speed in speed_tols:
        print(f'Speed tolerance: {tol_speed} m/s')
        # Preprocess data with current tolerance
        df = preprocess_data(pnom, hour_data, phi, tol_speed)
        
        for max_tol_points in tqdm(point_tols, desc="Point tolerance", leave=False):
            for ws in tqdm(window_sizes, desc="Window sizes", leave=False):
                stops, avg, _ = calculate_kpi_tolerance(
                    df.copy(), ws, tol_speed, max_tol_points
                )
                results.append({
                    'speed_tol': tol_speed,
                    'point_tol': max_tol_points,
                    'window_size': ws,
                    'num_stops': stops,
                    'avg_cf': avg
                })
    
    # Convert to DataFrame
    kpi_df = pd.DataFrame(results)
    
    # Create output directory
    data_type = "Original 1-hour" if hour_data else f"Synthetic 1-min {phi} phi"
    output_dir = f"Analysis/Tolerance Analysis/{data_type} data"
    os.makedirs(output_dir, exist_ok=True)
    
    # Save results
    kpi_df.to_excel(f"{output_dir}/{int(pnom)}MW_tolerance_analysis.xlsx", index=False)
    
    # Find optimal configuration
    valid_configs = kpi_df[kpi_df['num_stops'] <= MAX_ALLOWED_STOPS]
    
    if not valid_configs.empty:
        optimal = valid_configs.loc[valid_configs['avg_cf'].idxmax()]
    else:
        optimal = kpi_df.loc[kpi_df['num_stops'].idxmin()]
    
    # Print optimal results
    print(f"\nOptimal for {int(pnom)}MW ({data_type}):")
    print(f"  Speed tolerance: {optimal.speed_tol:.1f} m/s")
    print(f"  Point tolerance: {int(optimal.point_tol)} points")
    print(f"  Window size: {int(optimal.window_size)}")
    print(f"  Stops: {int(optimal.num_stops)} (Max allowed: {int(MAX_ALLOWED_STOPS)})")
    print(f"  Capacity factor: {optimal.avg_cf:.4f}\n\n")
    
    return optimal

# Execute analysis
tolerance_sensitivity_analysis(pnom=15, hour_data=True)
tolerance_sensitivity_analysis(pnom=22, hour_data=True)
tolerance_sensitivity_analysis(pnom=15, hour_data=False, phi=0.8)
tolerance_sensitivity_analysis(pnom=22, hour_data=False, phi=0.8)
tolerance_sensitivity_analysis(pnom=15, hour_data=False, phi=0.9)
tolerance_sensitivity_analysis(pnom=22, hour_data=False, phi=0.9)