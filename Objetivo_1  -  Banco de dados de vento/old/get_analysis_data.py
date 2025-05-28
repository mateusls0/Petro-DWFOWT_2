import pandas as pd
import numpy as np

def calculate_power(csv_path, excel_path, output_csv_path="analysis_data.csv", to_samir=False):
    # Read input data
    if to_samir:
        df = pd.read_csv(csv_path, sep=";", decimal=",")
    else:
        df = pd.read_csv(csv_path)
    
    # Calculate wind speed magnitude
    df['ws value'] = np.sqrt(df['100u']**2 + df['100v']**2)
    wind_speed = df['ws value']
    
    # Load power curve with European decimal format
    power_curve = pd.read_excel(
        excel_path,
        decimal=',',
        usecols=['Wind Speed [m/s]', 'Power [pu]']
    ).sort_values('Wind Speed [m/s]')

    # Ensure 'Wind Speed [m/s]' in power_curve is float
    power_curve['Wind Speed [m/s]'] = power_curve['Wind Speed [m/s]'].astype(float)

    # Convert wind_speed DataFrame to 1D Series (if needed)
    if isinstance(wind_speed, pd.DataFrame):
        wind_speed = wind_speed.squeeze()  # Converts single-column DataFrame to Series
    
    # Create DataFrame with 1D wind speed data and index
    wind_df = pd.DataFrame(
        {'Wind Speed [m/s]': wind_speed.values},  # Use the Series directly
    )

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
            (power_curve_df['Power [pu]'] == 1) &
            (power_curve_df['previous_power'] < 1)
        )

        # Filter rows that meet the condition and find the maximum wind speed
        valid_transitions = power_curve_df[condition_rated]
        rated_speed = valid_transitions['Wind Speed [m/s]'].max()
        
        # Calculate the cut out speed
        # Define the condition: current Power is 1 and next Power is 0
        condition_cut_out = (
            (power_curve_df['Power [pu]'] == 1) &
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
        def calculate_power2(wind_speed):
            if wind_speed < cut_in_speed:
                return 0.0
            elif cut_in_speed <= wind_speed < rated_speed:
                # Cubic interpolation logic 
                return np.polyval(coeff, wind_speed)
            elif rated_speed <= wind_speed <= cut_out_speed:
                return 1.0
            else:
                return 0.0
        
        # Calculate available power
        p_max_pu_wind_available = wind_df["Wind Speed [m/s]"].apply(calculate_power2).rename("Power [pu]")

        return p_max_pu_wind_available.values
    
    cubic_fitting_power_curve(power_curve, wind_df)
    
    # Restore original time order
    p_max_pu_wind_available = cubic_fitting_power_curve(power_curve, wind_df)

    # Get maximum power output as a comparison between the previous ones
    p_max_pu = p_max_pu_wind_available

    df["p (pu)"] = p_max_pu
    
    # Save and return
    if to_samir:
        df.to_csv(output_csv_path, index=False, sep=";", decimal=",")
    else:
        df.to_csv(output_csv_path, index=False)
    return df

calculate_power("data_analysis_samir.csv", "Curva de potencia.xlsx", output_csv_path="complete_data_samir.csv", to_samir=True)