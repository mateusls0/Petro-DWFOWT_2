import pandas as pd
import numpy as np
from scipy.stats import weibull_min
from scipy.special import gamma
import matplotlib.pyplot as plt

def main(pnom):

    if pnom == 15:
        height = 150
    else:
        height = 170

    # ----------------------------------------------------
    # 1. Load and Prepare Hourly Data
    # ----------------------------------------------------
    np.random.seed(10)

    # Load data
    data = pd.read_excel("buzios_metocean.xlsx").iloc[1:]

    # Convert 'time' to datetime and set as index
    data['time'] = pd.to_datetime(data['time'])
    data.set_index('time', inplace=True)

    # Convert wind speed to numeric and handle errors
    data['wspd100'] = pd.to_numeric(data['wspd100'], errors='coerce')  # Convert to numeric, invalid → NaN

    # Apply scaling and rename
    data[f'wspd{int(height)}'] = data['wspd100'] * (height / 100)**0.12
    data = data[[f'wspd{int(height)}']].copy()  # Keep only the wspd150 column

    # Drop NaN/infinite values
    data = data.replace([np.inf, -np.inf], np.nan).dropna()

    # Extract month
    data["month"] = data.index.month

    # Initialize dictionaries to store monthly parameters
    monthly_k = {}
    monthly_lambda = {}

    # Fit Weibull parameters for each month
    for month in range(1, 13):
        # Subset data for the month (ensure numeric and >0)
        monthly_data = data.loc[data["month"] == month, f'wspd{int(height)}'].values
        monthly_data = monthly_data[(monthly_data > 0) & (~np.isnan(monthly_data))]  # Remove NaN/negative

        if len(monthly_data) == 0:
            print(f"Month {month}: No valid data. Skipping.")
            continue

        try:
            # Fit Weibull distribution (fix location=0)
            k, loc, scale = weibull_min.fit(monthly_data.astype(float), floc=0)  # Force float type
        except Exception as e:
            print(f"Month {month}: Fit failed - {e}")
            continue

        # Calculate theoretical mean for validation
        theoretical_mean = scale * gamma(1 + 1/k)
        observed_mean = np.mean(monthly_data)
        
        # Store parameters
        monthly_k[month] = k
        monthly_lambda[month] = scale
        
        print(f"Month {month}:")
        print(f"  k = {k:.2f}, λ = {scale:.2f}")
        print(f"  Theoretical Mean = {theoretical_mean:.2f} m/s, Observed Mean = {observed_mean:.2f} m/s\n")

    # Plot monthly k values
    months = list(monthly_k.keys())
    k_values = [monthly_k[m] for m in months]
    plt.plot(months, k_values, marker='o')
    plt.title("Monthly Weibull Shape Parameter (k)")
    plt.xlabel("Month")
    plt.ylabel("k")
    plt.xticks(range(1, 13), ["Jan", "Feb", "Mar", "Apr", "May", "Jun", 
                            "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])
    plt.grid(True)
    plt.show()

    # ------------------------------
    # 2. Modified Hybrid Generator
    # ------------------------------
    def generate_hybrid_weibull(hourly_mean, k, phi=0.8, burn_in=30):
        """Generate 1-min wind speeds with Weibull distribution and AR(1) persistence."""
        if hourly_mean <= 0:
            return np.zeros(60)
        
        gamma_term = gamma(1 + 1/k)
        lam = hourly_mean / gamma_term
        samples = weibull_min.rvs(k, scale=lam, size=60 + burn_in, random_state=10)
        
        ar_filtered = np.zeros_like(samples)
        ar_filtered[0] = samples[0]
        for t in range(1, len(samples)):
            ar_filtered[t] = phi * ar_filtered[t-1] + (1 - phi) * samples[t]
        
        final_samples = ar_filtered[burn_in:]
        final_samples = np.clip(final_samples, 0, None)
        current_mean = np.mean(final_samples)
        
        if current_mean > 0:
            final_samples *= (hourly_mean / current_mean)
        
        return final_samples

    # ------------------------------
    # 3. Main Processing
    # ------------------------------
    phi_values = [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    combined_df = pd.DataFrame()

    for phi in phi_values:
        print(f"\n{'='*40}\nProcessing phi = {phi:.1f}\n{'='*40}")
        
        minute_records = []
        for hour_time, row in data.iterrows():
            month = hour_time.month
            k = monthly_k[month]
            hourly_mean = row[f'wspd{int(height)}']
            
            try:
                samples = generate_hybrid_weibull(hourly_mean, k, phi)
            except Exception as e:
                print(f"Error at {hour_time}: {e}")
                samples = np.full(60, hourly_mean)
                
            minute_index = pd.date_range(start=hour_time, periods=60, freq='min')
            df = pd.DataFrame({'wind_speed': samples}, index=minute_index)
            minute_records.append(df)
        
        # Create temporary dataframe for current phi
        temp_df = pd.concat(minute_records).sort_index()
        
        # Format column name (phi=0.1 -> wspd150_phi01)
        phi_str = f"{int(phi*10):02d}"  # Convert 0.1 to "01"
        temp_df = temp_df.rename(columns={'wind_speed': f'wspd{int(height)}_phi{phi_str}'})
        
        # Merge with combined dataframe
        if combined_df.empty:
            combined_df = temp_df
        else:
            combined_df = combined_df.join(temp_df, how='outer')
        
        # Generate and save individual plots
        plt.figure(figsize=(15, 6))
        plt.plot(temp_df.index, temp_df.iloc[:, 0], 
                linewidth=0.5, 
                color='steelblue',
                alpha=0.7)
        
        plt.title(f'1-Minute Wind Speed (φ={phi:.1f})', fontsize=14)
        plt.xlabel('Date', fontsize=12)
        plt.ylabel('Wind Speed (m/s)', fontsize=12)
        plt.grid(True, alpha=0.3)
        
        # Add this line to set consistent y-axis limits
        plt.ylim(0, 60)
        
        plt.savefig(f'Analysis/1-min wind speed phi variation - {int(height)}m/wind_speed_phi{phi_str}.png', dpi=300, bbox_inches='tight')
        plt.close()

    # ------------------------------
    # 4. Save Combined Data
    # ------------------------------
    # Reorder columns numerically
    column_order = [f'wspd{int(height)}_phi{int(phi*10):02d}' for phi in phi_values]
    combined_df = combined_df[column_order]

    # Save to CSV
    combined_df.to_csv(f'wind_speed_1min_{int(height)}m.csv', 
                    float_format='%.4f',
                    index_label='datetime')

    print("\nFinal DataFrame Columns:")
    print(combined_df.columns)
    print(f"\nSaved combined data with {len(combined_df):,} rows")


pnom = 22
main(pnom)