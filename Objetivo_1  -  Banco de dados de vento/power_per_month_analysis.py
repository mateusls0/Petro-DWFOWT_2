import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import calendar

def main(pnom):

    if pnom == 15:
        height = 150
    else:
        height = 170

    # Load power curve with European decimal format
    power_curve = pd.read_excel(
        str(int(pnom))+'MW_power_curve.xlsx',
        decimal=',',
        usecols=['Wind Speed [m/s]', 'Power [pu]']
    ).sort_values('Wind Speed [m/s]')

    # Ensure 'Wind Speed [m/s]' in power_curve is float
    power_curve['Wind Speed [m/s]'] = power_curve['Wind Speed [m/s]'].astype(float)

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

    # Read the Excel file, skip the unit row, and handle decimal commas
    # Load wind speed data with proper datetime format
    wind_speed = pd.read_excel(
        'buzios_metocean.xlsx',
        index_col='time',
        parse_dates=True,
        date_format='%Y/%m/%d %H:%M'
    )['wspd100'].sort_index().iloc[1:]

    # Convert index to datetime
    wind_speed.index = pd.to_datetime(wind_speed.index)

    # Convert to numeric type and handle non-numeric values
    wind_speed = pd.to_numeric(wind_speed, errors='coerce')

    # Correct wind speed from 100m to 150m
    wind_speed = wind_speed.rename('wspd'+str(int(height))) * (height / 100) ** 0.12

    # Transform wind speed series into dataframe
    wind_speed = wind_speed.to_frame()

    # Get generated power based on power curve
    wind_speed['power_pu'] = cubic_fitting_power_curve(power_curve, wind_speed)

    # Rename dataframe
    df = wind_speed.copy()

    # Extract year, month, and time within month (day + hour/24)
    df['year'] = df.index.year
    df['month'] = df.index.month
    df['time_in_month'] = df.index.day + df.index.hour / 24
 
    # Get unique years and assign colors
    years = sorted(df['year'].unique())[:11]

    # Set months names
    month_names = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]

    # Create one figure per year
    for year in years:
        # Create figure with 4x3 subplots
        fig, axes = plt.subplots(4, 3, figsize=(18, 15))
        plt.subplots_adjust(top=0.9)  # Adjust top to make space for the suptitle
        axes = axes.flatten()
        
        # Plot each month's data for the current year
        for i, month in enumerate(range(1, 13)):
            ax = axes[i]
            # Filter data for the current year and month
            year_month_data = df[(df['year'] == year) & (df['month'] == month)]
            
            if not year_month_data.empty:
                # Determine the maximum day in the month for this specific year
                max_day = year_month_data.index.day.max()
            else:
                max_day = 31  # Fallback if no data
            
            # Generate x-axis ticks
            tick_days = sorted(list({1, 5, 10, 15, 20, 25, max_day}))
            ax.set_xticks(tick_days)
            ax.set_xlim(1, max_day + 1)
            ax.set_ylim(0, pnom + 2)
            
            # Plot the data for this month
            if not year_month_data.empty:
                ax.plot(
                    year_month_data['time_in_month'], 
                    year_month_data['power_pu'] * pnom,
                    color='navy', 
                    linewidth=0.5
                )
            
            # Set subplot title and labels
            month_name = month_names[i]
            ax.set_title(month_name)
            ax.set_xlabel('Day of Month')
            ax.set_ylabel('Max Power (MW)')
        
        # Set figure title and save
        fig.suptitle(f'Year {int(year)}', fontsize=16)
        plt.tight_layout()
        plt.savefig(f'Analysis/{int(pnom)}MW available power/{int(pnom)}_MW_monthly_power_{int(year)}.png', bbox_inches='tight')
        plt.close()  # Close the figure to free memory


    # Calculate monthly energy sums (power_pu * Pnom * 1 hour interval)
    df['energy_mwh'] = df['power_pu'] * pnom  # Convert to MW and sum over hours (MWh)

    # Create pivot table with year as index and month as columns
    pivot_table = df.groupby(['year', 'month'])['energy_mwh'].sum().unstack()

    # Rename columns to month names using the predefined list
    pivot_table.columns = month_names

    # Format the output
    summary_df = pivot_table.reset_index()
    summary_df['year'] = summary_df['year'].astype(int)
    summary_df = summary_df.iloc[:11]

    # Save to Excel with formatting
    with pd.ExcelWriter(f'Analysis/{int(pnom)}MW available power/{int(pnom)}MW_monthly_energy_summary.xlsx') as writer:
        summary_df.to_excel(writer, index=False, sheet_name='Monthly Energy')
        
        # Get xlsxwriter objects for formatting
        workbook = writer.book
        worksheet = writer.sheets['Monthly Energy']
        
        # Add thousands separator format
        num_format = workbook.add_format({'num_format': '#,##0.0'})
        
        # Apply formatting to energy columns
        for col_num in range(2, len(month_names) + 2):
            worksheet.set_column(col_num, col_num, 12, num_format)
        
        # Format year column
        worksheet.set_column(0, 0, 6)

    print("Monthly energy summary saved to monthly_energy_summary.xlsx")

    # Create Power heatmap from the summary_df
    plt.figure(figsize=(14, 10))
    ax = sns.heatmap(summary_df.set_index('year'), 
                    annot=True, 
                    fmt=",.1f",
                    cmap="YlGnBu",
                    linewidths=.5,
                    annot_kws={"size": 8},
                    cbar_kws={'label': 'Energy Generated (MWh)'})

    # Customize plot
    plt.title(f'{int(pnom)}MW Turbine Monthly Energy Generation (2007-2017)', pad=20, fontsize=14)
    plt.xlabel('Month', fontsize=12)
    plt.ylabel('Year', fontsize=12)
    ax.set_xticklabels(month_names, rotation=45)
    ax.set_yticklabels(summary_df['year'].astype(int), rotation=0)

    # Save and show plot
    plt.tight_layout()
    plt.savefig(f'Analysis/{int(pnom)}MW available power/{int(pnom)}MW_energy_heatmap.png', dpi=300, bbox_inches='tight')
    plt.show()

    # Create month name to number mapping
    month_to_num = {month_names[i]: i+1 for i in range(len(month_names))}

    # Set year as index
    p_capacity_df = summary_df.set_index('year')

    # Create DataFrame with number of days for each month/year
    days_df = pd.DataFrame(index=p_capacity_df.index, columns=p_capacity_df.columns)

    for year in days_df.index:
        for month in days_df.columns:
            days_df.loc[year, month] = calendar.monthrange(year, month_to_num[month])[1]

    # Convert to integers and calculate normalized values
    days_df = days_df.astype(int)
    normalized_df = p_capacity_df.div(days_df) / 24 / pnom

    # Reset index if needed
    normalized_df = normalized_df.reset_index().set_index('year')

    # Get mean PC
    mean_pc = np.nanmean(normalized_df)

    # Create Power Capacity heatmap from the summary_df
    plt.figure(figsize=(14, 10))
    ax = sns.heatmap(normalized_df, 
                    annot=True, 
                    fmt=",.3f",
                    cmap="YlGnBu",
                    linewidths=.5,
                    annot_kws={"size": 8},
                    cbar_kws={'label': 'Capacity Factor (p.u.)'})

    # Customize plot
    plt.title(f'{int(pnom)}MW Turbine Monthly Capacity Factor (2007-2017)\nMean Capacity Factor: {round(mean_pc, 3)}', pad=20, fontsize=14)
    plt.xlabel('Month', fontsize=12)
    plt.ylabel('Year', fontsize=12)
    ax.set_xticklabels(month_names, rotation=45)
    ax.set_yticklabels(summary_df['year'].astype(int), rotation=0)

    # Save and show plot
    plt.tight_layout()
    plt.savefig(f'Analysis/{int(pnom)}MW available power/{int(pnom)}MW_capacity_factor_heatmap.png', dpi=300, bbox_inches='tight')
    plt.show()

pnom=15
main(pnom)