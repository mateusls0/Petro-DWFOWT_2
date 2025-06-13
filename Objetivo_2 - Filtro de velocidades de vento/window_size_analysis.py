import pandas as pd
# pd.set_option('future.no_silent_downcasting', True)
import numpy as np
import matplotlib.pyplot as plt
from tqdm import tqdm  # For progress bar

def preprocess_data(pnom, hour_data=True, phi=0.8):
    """Load and preprocess data once for a given pnom"""
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
            nrows=365*24*60 # 1 year
        )[f'wspd{int(height)}_phi{str(phi).replace('.','')}'].sort_index()
    
    # Preprocess wind data
    wind_speed = (wind_speed
                  .pipe(pd.to_numeric, errors='coerce')
                  .rename(f'wspd{height}')
                  .to_frame())
    
    if hour_data:
        wind_speed = wind_speed * (height/100)**0.12

    # Calculate maximum power output based on wind availability, using cut in, cut out and cubic fitting of power curve
    def cubic_fitting_power_curve(power_curve, wind_df):
        
        # Calculate the cut in speed
        power_curve_df = power_curve
        power_curve_df['next_power'] = power_curve_df['Power [pu]'].shift(-1)
        power_curve_df['previous_power'] = power_curve_df['Power [pu]'].shift(1)

        # Define the condition: current Power is  0 and next Power is more than 0
        condition_cut_in = (
            (power_curve_df['Power [pu]'] == 0) &
            (power_curve_df['next_power'] > 0)
        )

        # Filter rows that meet the condition and find the maximum wind speed
        valid_transitions = power_curve_df[condition_cut_in]
        cut_in_speed = valid_transitions['Wind Speed [m/s]'].max()

        # Calculate the rated speed
        # Define the condition: current Power is 1 and previous Power less than 1
        condition_rated = (
            (abs(power_curve_df['Power [pu]'] - 1) <= 1e-3) &
            (1 - power_curve_df['previous_power'] >= 1e-3)
        )

        # Filter rows that meet the condition and find the maximum wind speed
        valid_transitions = power_curve_df[condition_rated] 
        rated_speed = valid_transitions['Wind Speed [m/s]'].max()
        
        # Calculate the cut out speed
        # Define the condition: current Power is 1 and next Power is 0
        condition_cut_out = (
            (power_curve_df['Power [pu]'] >= 1) &
            (power_curve_df['next_power'] == 0)
        )

        # Filter rows that meet the condition and find the maximum wind speed
        valid_transitions = power_curve_df[condition_cut_out]
        cut_out_speed = valid_transitions['Wind Speed [m/s]'].max()

        # Make power pu cubic fitting for wind speeds between cut in and rated wind speed
        # Filter rows where wind speed is between cut in and rated speed (inclusive)
        filtered_df = power_curve_df[
            (power_curve_df['Wind Speed [m/s]'] >= cut_in_speed) &
            (power_curve_df['Wind Speed [m/s]'] <= rated_speed)
        ]

        # Extract wind speeds and power values as separate arrays
        wind_speeds_array = filtered_df['Wind Speed [m/s]'].to_numpy()
        power_values_array = filtered_df['Power [pu]'].to_numpy()

        # Get cubic polynomial coefficients
        coeff =  np.polyfit(wind_speeds_array, power_values_array, 3)

        # Define calculation of power curve
        def calculate_power(wind_speed):
            if wind_speed < cut_in_speed:
                return 0.0
            elif cut_in_speed <= wind_speed < rated_speed:
                # Cubic interpolation logic 
                return min(np.polyval(coeff, wind_speed), 1.0)
            elif rated_speed <= wind_speed <= cut_out_speed:
                return 1.0
            else:
                return 0.0
        
        # Calculate available power
        p_max_pu_wind_available = wind_df["wspd"+str(int(height))].apply(calculate_power).rename("Power [pu]")

        return p_max_pu_wind_available.values

    wind_speed['power_pu'] = cubic_fitting_power_curve(power_curve, wind_speed)
    return wind_speed[:-1]  # Remove last row as original


def calculate_kpi(df, window_size):
    """Calculate KPI for a given window size using preprocessed data"""
    # Precompute availability mask
    v_cut_in, v_cut_out = 3, 25 
    mask = (df.iloc[:, 0] >= v_cut_in) & (df.iloc[:, 0] <= v_cut_out)
    
    # Create shifted masks
    shifted = [mask.shift(-s, fill_value=False) for s in range(window_size)]
    df['availability'] = pd.concat(shifted, axis=1).all(axis=1)
    
    # Calculate transitions
    transitions = (df['availability'] & ~df['availability'].shift(-1, fill_value=False)).sum()
    
    # Calculate available power
    df['available_power'] = df['power_pu'] * df['availability']
    avg_power = df['available_power'].mean()
    
    return transitions, avg_power, df

def main(pnom, hour_data=True, phi=0.8):
    # Define maximum allowed stops
    MAX_ALLOWED_STOPS = 10000/25 # stops per year - 10000 stops on lifetime of 25 years
    if hour_data:
        MAX_ALLOWED_STOPS *= 11  # 400 stops per year times 11 years
    
    # Main execution
    df = preprocess_data(pnom, hour_data, phi)
    window_sizes = range(1, 51)
    results = []

    # Add progress bar
    for ws in tqdm(window_sizes, desc="Analyzing window sizes", unit="window"):
        stops, avg, _ = calculate_kpi(df.copy(), ws)
        results.append({
            'window_size': ws,
            'num_stops': stops,
            'avg_cf': avg  # avg_pf is capacity factor
        })

    kpi_df = pd.DataFrame(results)
    
    # Find optimal window size based on new criteria:
    # 1. Number of stops <= MAX_ALLOWED_STOPS
    # 2. Maximum capacity factor (avg_pf)
    valid_windows = kpi_df[kpi_df['num_stops'] <= MAX_ALLOWED_STOPS]
    
    if not valid_windows.empty:
        # Among valid windows, select one with max capacity factor
        optimal_row = valid_windows.loc[valid_windows['avg_cf'].idxmax()]
    else:
        # If no window meets stop criteria, select one with minimum stops
        optimal_row = kpi_df.loc[kpi_df['num_stops'].idxmin()]
    
    # Add this line to save to Excel
    if hour_data:
        kpi_df.to_excel(f'Analysis/Original 1-hour data/{int(pnom)}MW KPIs analysis results.xlsx', index=False)
    else:
        kpi_df.to_excel(f'Analysis/Synthetic 1-min {str(phi)} phi data/{int(pnom)}MW KPIs analysis results.xlsx', index=False)

    # Create plots with explicit axes objects
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(15, 8))
    
    # Plot 1: Number of stops
    ax1.plot(kpi_df.window_size, kpi_df.num_stops, 'b-o')
    ax1.set_title('Turbine Number of Stops', fontsize=14)
    ax1.set_ylabel('Number of Stops', fontsize=12)
    ax1.grid(True)
    
    # Add horizontal line at MAX_ALLOWED_STOPS
    ax1.axhline(y=MAX_ALLOWED_STOPS, color='r', linestyle='--', alpha=0.7)
    ax1.text(1, MAX_ALLOWED_STOPS*1.05, f'Max allowed stops ({int(MAX_ALLOWED_STOPS)})', 
             fontsize=12, color='r')

    # Plot 2: Capacity Factor
    ax2.plot(kpi_df.window_size, kpi_df.avg_cf, 'r-o')
    ax2.set_title('Turbine Capacity Factor', fontsize=14)
    ax2.set_ylabel('Average Capacity Factor', fontsize=12)
    ax2.grid(True)
    
    # Add vertical line at optimal window size
    opt_win = int(optimal_row.window_size)
    ax2.axvline(x=opt_win, color='gray', linestyle='--', alpha=0.7)
    
    # Add text label at top of plot
    xmin, xmax = ax2.get_xlim()
    x_text = (opt_win - xmin)/(xmax - xmin) + 0.07

    y_text = 0.1

    ax2.text(x_text, y_text, 
             f'Optimal window = {opt_win}',
             fontsize=12, 
             ha='center', 
             va='top',
             transform=ax2.transAxes,
             bbox=dict(boxstyle="round,pad=0.3", 
                      fc="white", 
                      ec="gray", 
                      lw=0.5))

    # Common elements
    plt.xlabel('Window size', fontsize=12)
    fig.suptitle(f'KPI analysis for {int(pnom)}MW Turbine', fontsize=14)
    plt.tight_layout()

    if hour_data:
        plt.savefig(f'Analysis/Original 1-hour data/{int(pnom)}MW KPIs analysis.png', dpi=300, bbox_inches='tight')
    else:
        plt.savefig(f'Analysis/Synthetic 1-min {str(phi)} phi data/{int(pnom)}MW KPIs analysis.png', dpi=300, bbox_inches='tight')
    # plt.show()

    if hour_data:
        print(f"1-hour data and {int(pnom)}MW turbine\nMaximum stops allowed: {int(MAX_ALLOWED_STOPS)}")
        print(f"Optimal window size: {int(opt_win)} with {int(optimal_row.num_stops)} stops")
        print(f"Maximum capacity factor: {optimal_row.avg_cf:.3f}\n")
    else:
        print(f"1-minute data phi = {str(phi)} and {int(pnom)}MW turbine\nMaximum stops allowed: {int(MAX_ALLOWED_STOPS)}")
        print(f"Optimal window size: {int(opt_win)} with {int(optimal_row.num_stops)} stops")
        print(f"Maximum capacity factor: {optimal_row.avg_cf:.3f}\n")

# Execute analysis
main(pnom=15, hour_data=True)
main(pnom=22, hour_data=True)
main(pnom=15, hour_data=False, phi=0.8)
main(pnom=22, hour_data=False, phi=0.8)
main(pnom=15, hour_data=False, phi=0.9)
main(pnom=22, hour_data=False, phi=0.9)