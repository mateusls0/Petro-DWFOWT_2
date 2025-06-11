import pandas as pd
import matplotlib.pyplot as plt

def plot_figures(results_filepath, wind_speed_filepath):
    # Prefix for Figures directory
    prefix = "Figures/09-05-25 Apresentacao/"

    # Read Excel file
    sheet_name = "Resultados completos"
    df = pd.read_excel(results_filepath, sheet_name=sheet_name, decimal=',')

    # Create hourly sequence for x-axis
    df['Hour'] = range(1, len(df) + 1)

    # Define explicit colors for each component
    colors = {
        'Load': '#1f77b4',          # Blue
        'BatteryCharge': '#9467bd', # Purple
        'CableLosses': '#d62728',   # Red
        'WindPower': '#2ca02c',     # Green
        'BatteryDischarge': '#ff7f0e' # Orange
    }

    # Create figure
    plt.figure(figsize=(12, 7))

    # First stack: Load, Battery Charge, Cable Losses
    plt.stackplot(df['Hour'], 
                df['Load (MW)']+0.2+df['Battery Charge (MW)']+df['Cable Losses (MW)'],
                labels=['Load + Battery Charge + Cable Losses + 0.2'],
                colors=[colors['Load']],
                alpha=0.2)

    # Second stack: Wind Power and Battery Discharge
    plt.stackplot(df['Hour'], 
                df['Wind Power (MW)']+df['Battery Discharge (MW)'],
                labels=['Wind Power + Battery Discharge'],
                colors=[colors['WindPower']],
                alpha=0.2)

    # Add individual lines with matching colors
    plt.plot(df['Hour'], df['Load (MW)']+0.2+df['Battery Charge (MW)']+df['Cable Losses (MW)'], color=colors['Load'], linewidth=1.2, alpha=1)
    plt.plot(df['Hour'], df['Wind Power (MW)']+df['Battery Discharge (MW)'], color=colors['WindPower'], linewidth=1.2, alpha=1)

    # Add labels and title
    plt.xlabel('Hour', fontsize=12)
    plt.ylabel('Power (MW)', fontsize=12)
    plt.title('Power System Analysis: Load vs Generation', fontsize=14, pad=20)
    plt.legend(loc='upper left', frameon=False)

    # Save figure
    plt.savefig(prefix + 'power_analysis.png', dpi=300, bbox_inches='tight')
    plt.show()

    #######################################################################################################################################################################################################

    # Read Excel file
    sheet_name = "Resultados completos"
    df = pd.read_excel(results_filepath, sheet_name=sheet_name, decimal=',')
    size = len(df.index)

    # Define explicit colors
    colors = {
        'BatteryCharge': '#2ca02c',        # Green
        'BatteryChargeLosses': '#98df8a',  # Light Green
        'BatteryDischarge': '#ff7f0e',     # Orange
        'BatteryDischargeLosses': '#ffbb78', # Light Orange
        'StateOfCharge': '#1f77b4',        # Blue
        'SelfDischargeLosses': '#d62728'   # Red
    }

    # Prepare data
    def prep_data(series, prepend_value=None):
        """Prep data with optional prepended value and first 10 elements"""
        if prepend_value is not None:
            series = pd.concat([pd.Series([prepend_value]), series]).reset_index(drop=True)
        return series.iloc[:size]

    # Get first 10 values for each series
    batt_charge = prep_data(df['Battery Charge (MW)'])
    batt_charge_losses = prep_data(df['Battery Charging Losses (MW)'])
    batt_discharge = prep_data(df['Battery Discharge (MW)'])
    batt_discharge_losses = prep_data(df['Battery Discharging Losses (MW)'])
    soc = prep_data(df['State of Charge (MWh)'], prepend_value=4)
    self_discharge = prep_data(df['Battery Self-Discharge Losses (MW)'], prepend_value=0)

    # Create x-axis values
    hours = range(1, size + 1)

    # Create plot
    plt.figure(figsize=(12, 7))

    # Plot Battery Charge and Losses
    plt.plot(hours, batt_charge-batt_charge_losses, color=colors['BatteryCharge'], 
            linewidth=2, label='Battery Charge - Losses')

    # Plot Battery Discharge and Losses
    plt.plot(hours, -batt_discharge-batt_discharge_losses, color=colors['BatteryDischarge'], 
            linewidth=2, label='Battery Discharge - Losses')

    # Plot State of Charge and Self Discharge Losses
    plt.plot(hours, soc-self_discharge, color=colors['StateOfCharge'],
            linewidth=2)
    plt.stackplot(hours, soc-self_discharge, color=colors['StateOfCharge'],
            alpha=0.2, labels=['State of Charge - Self discharge'])

    # Add labels and title
    plt.xlabel('Hour'# plt.xticks(hours)
    , fontsize=12)
    plt.ylabel('Power (MW) / Energy (MWh)', fontsize=12)
    plt.title('Battery Performance and Loss Analysis', fontsize=14, pad=20)
    plt.legend(loc='lower left')

    # Save and show
    plt.tight_layout()
    plt.savefig(prefix + 'battery_analysis.png', dpi=300, bbox_inches='tight')
    plt.show()

    ###########################################################################################################################################################################################

    # Load the data from Excel
    df = pd.read_excel(wind_speed_filepath, decimal=',')  # Update file name/path if needed
    df['Datetime'] = pd.to_datetime(df['Datetime'], format='%d-%m-%Y %H:%M').iloc[:size]

    # Create hour sequence for x-axis (1, 2, 3...)
    hours = range(1, size + 1)

    # Create the plot
    plt.figure(figsize=(12, 6))
    plt.plot(hours, df['Wind Speed [m/s]'].iloc[:size], color='tab:blue', linewidth=1)

    # Format the plot
    plt.title('Wind Speed at 100m', fontsize=14)
    plt.xlabel('Hours', fontsize=12)
    plt.ylabel('Wind Speed (m/s)', fontsize=12)
    plt.grid(True, alpha=0.3)

    # Set x-axis ticks (show every 6 hours for better readability)
    # plt.xticks(range(1, len(hours)+1, 6))  # Adjust interval as needed

    # Save and show the plot
    plt.tight_layout()
    plt.savefig(prefix + 'wind_speed_plot.png', dpi=300)
    plt.show()