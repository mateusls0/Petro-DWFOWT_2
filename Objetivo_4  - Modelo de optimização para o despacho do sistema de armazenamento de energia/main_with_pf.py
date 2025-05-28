import pypsa
import pandas as pd
import numpy as np
from figures import plot_figures

def main(output_filename, simulation_size):
    # ==============================
    # 1. DATA PREPARATION
    # ==============================

    def load_input_data():
        """Load and preprocess input data from Excel files"""
        try:
            # Load wind speed data with proper datetime format
            wind_speed = pd.read_excel(
                'Velocidade dos ventos.xlsx',
                index_col='Datetime',
                parse_dates=True,
                date_format='%d/%m/%Y %H:%M'
            )['Wind Speed [m/s]'].sort_index()
            
            # Load load profile
            load_profile = pd.read_excel(
                'Curva de demanda.xlsx',
                index_col='Datetime',
                parse_dates=True,
                date_format='%d/%m/%Y %H:%M'
            )['load [MW]'].sort_index() * 10
            
            # Select first 10 time steps
            snapshots = wind_speed.index[:simulation_size]
            return (
                wind_speed.loc[snapshots], 
                load_profile.loc[snapshots], 
                snapshots
            )
            
        except Exception as e:
            print(f"Data loading failed: {e}")
            raise

    # Load and prepare data
    wind_speed, load_profile, snapshots = load_input_data()

    # ==============================
    # 2. NETWORK INITIALIZATION
    # ==============================

    # Create network with carrier definitions
    network = pypsa.Network(name="Offshore isolated wind-powered water injection system with battery")
    network.set_snapshots(snapshots)

    # Add required carriers
    network.add("Carrier", "Wind")
    network.add("Carrier", "Battery")
    network.add("Carrier", "AC")

    # Create buses with AC carrier
    network.add("Bus", "Node1", carrier="AC")
    network.add("Bus", "Node2", carrier="AC")

    # Add voltage base to buses
    v_nom = 10                # Nominal voltage in kW
    v_mag_set_pu = 1          # Voltage setpoint in pu

    network.buses["v_nom"] = v_nom
    network.buses["v_mag_pu_set"] = v_mag_set_pu

    # Include voltage variation limits - NOT WORKING IN PYPSA SO FAR
    v_variation = 0.01                                               # 5% maximum voltage variation from setpoint
    network.buses["v_mag_pu_min"] = v_mag_set_pu * (1 - v_variation) # Minimum voltage magnitude allowed
    network.buses["v_mag_pu_max"] = v_mag_set_pu * (1 + v_variation) # Maximum voltage magnitude allowed

    # ==============================
    # 3. WIND TURBINE SETUP
    # ==============================

    def create_wind_generator(network, wind_speed):
        """Configure wind turbine with power curve"""
        try:
            # Load power curve with European decimal format
            power_curve = pd.read_excel(
                'Curva de potencia.xlsx',
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
                index=network.snapshots
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
                def calculate_power(wind_speed):
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
                p_max_pu_wind_available = wind_df["Wind Speed [m/s]"].apply(calculate_power).rename("Power [pu]")

                return p_max_pu_wind_available.values
            
            cubic_fitting_power_curve(power_curve, wind_df)
            
            # Restore original time order
            p_max_pu_wind_available = cubic_fitting_power_curve(power_curve, wind_df)

            # Get maximum power output as a comparison between the previous ones
            # p_max_pu = p_max_pu_wind_available + 2/3
            p_max_pu = p_max_pu_wind_available + 2/3
            
            # Add generator to network
            network.add("Generator",
                "Wind Turbine",
                bus="Node1",
                control="Slack",    # Slack bus for power flow calculation
                carrier="Wind",
                p_nom=15,           # 15MW or 22MW NREL wind turbine
                committable=True,   # Can be shut off or on
                p_min_pu=0,         # Minimum dispatch is 0
                p_max_pu=p_max_pu,  # Maximum dispatch tied to wind availability
                # min_up_time=3,
                # min_down_time=3,
                min_up_time=0,      # Number of snapshots it must be on after it is turned on
                min_down_time=0,    # Number of snapshots it must be off after it is turned off
                ramp_limit_up=0.28,
                ramp_limit_down=0.28,
                marginal_cost=1
            )
            
        except Exception as e:
            print(f"Wind turbine configuration failed: {e}")
            raise

    create_wind_generator(network, wind_speed)

    # ==============================
    # 4. BATTERY STORAGE SETUP
    # ==============================

    def create_battery(network):
        """Configure battery as storage unit"""
        # Battery electrical parameters
        capacity = 5                    # 5 MWh of capacity
        p_nom = 1                       # 1 MW nominal power
        depth_of_discharge = 0.8        # 80% depth of discharge
        capacity *= depth_of_discharge  # Include DoD in battery capacity
        
        # Add battery to the network
        network.add("StorageUnit",
        "Battery",
        bus="Node1",
        carrier="Battery",             
        p_nom=p_nom,           
        max_hours=capacity/p_nom,          # Maximum hours the battery can dispatch at full capacity and power (Capacity in MWh/Maximum power in MW) 
        efficiency_store=0.95,             # Charging efficiency
        efficiency_dispatch=0.95,          # Discharging efficiency
        standing_loss=0.02/30/24,          # 0.5% hourly self-discharge
        state_of_charge_initial=capacity,  # 100% initial SOC
        cyclic_state_of_charge=False,      # Last SOC can be different from the first
        marginal_cost_storage=-1,
        marginal_cost=100
    )

    create_battery(network)

    # ==============================
    # 5. CABLE CONNECTION SETUP (AC LINE)
    # ==============================

    def create_ac_line(network):
        """Add AC line with impedance parameters"""
        # Cable electrical parameters (example values, adjust based on your cable specs)
        length = 1  # km
        r_per_km = 0.2   # Ω/km (resistance)
        x_per_km = 0.3   # Ω/km (reactance)
        s_nom = 25       # MVA (apparent power limit)
        
        network.add("Line",
            "AC Cable",
            bus0="Node1",
            bus1="Node2",
            r=r_per_km * length,
            x=x_per_km * length,
            s_nom=s_nom,
            type=None  # Can specify cable type if available - https://pypsa.readthedocs.io/en/latest/user-guide/components.html#line-types
        )

    create_ac_line(network)

    # ==============================
    # 6. LOAD CONFIGURATION
    # ==============================

    # Calculate reactive power
    power_factor = 0.93
    phi = np.arccos(power_factor)
    q_load = load_profile * np.tan(phi)

    network.add("Load",
        "Water Injection",
        bus="Node2",
        p_set=load_profile,   # Active power [MW]
        q_set=q_load          # Reactive power [MVAr]
    )

    # ==============================
    # 7. OPTIMIZATION SETUP
    # ==============================

    # Run optimization
    network.optimize.optimize_and_run_non_linear_powerflow(
        x_tol=1e-3,
        solver_name='gurobi',
        solver_options={
            'Threads': 6,
            'MIPGap': 1e-3,
            'TimeLimit': 3000,
            'LogToConsole': 1
        }
    )

    # ==============================
    # 8. EXPORT RESULTS
    # ==============================

    if network.model.status == "ok":
        # Create main results dataframe
        pf_results = pd.DataFrame(index=snapshots)

        # Bus voltage magnitudes
        pf_results['Voltage Magnitude Node1 (pu)'] = network.buses_t.v_mag_pu["Node1"]
        pf_results['Voltage Magnitude Node2 (pu)'] = network.buses_t.v_mag_pu["Node2"]

        # Bus voltage angles
        pf_results['Voltage Angle Node1 (rad)'] = network.buses_t.v_ang["Node1"]
        pf_results['Voltage Angle Node2 (rad)'] = network.buses_t.v_ang["Node2"]

        # Calculate power flow variables
        pf_results['Voltage Angle Difference (rad)'] = (
            network.buses_t.v_ang["Node1"] - network.buses_t.v_ang["Node2"]
        )
        
        pf_results['Line Loading (%)'] = (
            np.sqrt(network.lines_t.p0["AC Cable"].abs()**2 + network.lines_t.q0["AC Cable"].abs()**2) / network.lines.s_nom["AC Cable"] * 100
        )
        
        # Add line parameters
        pf_results['Line Active Power (MW)'] = network.lines_t.p0["AC Cable"]
        pf_results['Line Reactive Power (MVAr)'] = network.lines_t.q0["AC Cable"]
        
        # Check constraints
        max_loading = pf_results['Line Loading (%)'].max()
        angle_diff = pf_results['Voltage Angle Difference (rad)'].abs().max()
        
        print(f"\nPower Flow Validation:")
        print(f"Maximum line loading: {max_loading:.1f}%")
        print(f"Maximum voltage angle difference: {angle_diff:.4f} rad")
        
        if max_loading > 100:
            print("Warning: Line overload detected!")
        if angle_diff > 0.35:  # ~20 degrees
            print("Warning: Excessive voltage angle difference!")

        # Format numeric columns
        numeric_cols = pf_results.select_dtypes(include='number').columns
        pf_results[numeric_cols] = pf_results[numeric_cols].round(3)
        
        # Create main results dataframe
        results = pd.DataFrame(index=snapshots)

        # Power values
        results['Wind Power (MW)'] = network.generators_t.p["Wind Turbine"]
        results['Cable Flow (MW)'] = network.lines_t.p0["AC Cable"]
        results['Load (MW)'] = network.loads_t.p["Water Injection"]

        # Reactive Power values
        results['Wind Reactive Power (MVAr)'] = network.generators_t.q["Wind Turbine"]
        results['Cable Flow Reactive (MVAr)'] = network.lines_t.q0["AC Cable"]
        results['Load Reactive (MVAr)'] = network.loads_t.q["Water Injection"]
        
        # Battery values
        results['Battery Charge (MW)'] = network.storage_units_t.p_store["Battery"]
        results['Battery Discharge (MW)'] = network.storage_units_t.p_dispatch["Battery"]
        results['State of Charge (MWh)'] = network.storage_units_t.state_of_charge["Battery"]
        
        # 1. CALCULATE CABLE LOSSES
        results['Cable Losses (MW)'] = (
            network.lines_t.p0["AC Cable"] + 
            network.lines_t.p1["AC Cable"]
        ).abs()  # Actual power losses from line flow difference
        
        # 2. GET BATTERY EFFICIENCIES FROM NETWORK
        battery_params = network.storage_units.loc["Battery"]
        efficiency_store = battery_params["efficiency_store"]
        efficiency_dispatch = battery_params["efficiency_dispatch"]
        
        # 3. CALCULATE BATTERY LOSSES
        charging_loss = results['Battery Charge (MW)'] * (1 - efficiency_store)
        discharging_loss = results['Battery Discharge (MW)'] * (1/efficiency_dispatch - 1)
        
        # Calculate self-discharge losses (standing losses)
        standing_loss = battery_params["standing_loss"]
        initial_soc = battery_params["state_of_charge_initial"]
        soc = network.storage_units_t.state_of_charge["Battery"]
        previous_soc = soc.shift(1, fill_value=initial_soc)
        self_discharge_loss = previous_soc * standing_loss
        
        results['Battery Charging Losses (MW)'] = charging_loss
        results['Battery Discharging Losses (MW)'] = discharging_loss
        results['Battery Self-Discharge Losses (MW)'] = self_discharge_loss
        results['Total Battery Losses (MW)'] = charging_loss + discharging_loss + self_discharge_loss
        
        results['Total Losses (MW)'] = results['Cable Losses (MW)'] + results['Total Battery Losses (MW)']
        
        # Cost calculations
        results['Wind Cost (€)'] = results['Wind Power (MW)'] * network.generators.marginal_cost["Wind Turbine"]
        results['Battery Cost (€)'] = results['Battery Discharge (MW)'] * network.storage_units.marginal_cost["Battery"]
        results['Total Hourly Cost (€)'] = results['Wind Cost (€)'] + results['Battery Cost (€)']

        # Format numeric columns
        numeric_cols = results.select_dtypes(include='number').columns
        results[numeric_cols] = results[numeric_cols].round(3)
        
        # Add total cost as final row
        total_cost = pd.DataFrame({
            'Total Operational Cost (€)': results['Wind Cost (€)'].sum() + results['Battery Cost (€)'].sum(),
            'Total Wind Cost (€)': [results['Wind Cost (€)'].sum()],
            'Total Battery Cost (€)': [results['Battery Cost (€)'].sum()],
            'Total Losses (MWh)': [results['Total Losses (MW)'].sum()],
        }, index=['Totals']).round(3)
        
        # Then override specific column with 2 decimals
        total_cost['Total Operational Cost (€)'] = total_cost['Total Operational Cost (€)'].round(2)
        total_cost['Total Wind Cost (€)'] = total_cost['Total Wind Cost (€)'].round(2)
        total_cost['Total Battery Cost (€)'] = total_cost['Total Battery Cost (€)'].round(2)
        
        # Create Excel writer and save
        with pd.ExcelWriter(output_filename) as writer:
            # Write power flow sheet
            pf_results.to_excel(writer, sheet_name='Fluxo de potência')
            
            # Main results sheet
            results.to_excel(writer, sheet_name='Resultados completos')
            
            # Summary sheet
            total_cost.to_excel(writer, sheet_name='Sumário')
            
            # Detailed summary
            summary = pd.DataFrame({
                'Metric': [
                    'Total Operational Cost', 
                    'Total Wind Generation', 
                    'Total Battery Discharge',
                    'Total Battery Charge',
                    'Total Load Served', 
                    'Total Cable Losses',
                    'Total Battery Charging Losses',
                    'Total Battery Discharging Losses',
                    'Total Battery Self-Discharge Losses'
                ],
                'Value': [
                    network.objective,
                    results['Wind Power (MW)'].sum(),
                    results['Battery Discharge (MW)'].sum(),
                    results['Battery Charge (MW)'].sum(),
                    results['Load (MW)'].sum(),
                    results['Cable Losses (MW)'].sum(),
                    results['Battery Charging Losses (MW)'].sum(),
                    results['Battery Discharging Losses (MW)'].sum(),
                    results['Battery Self-Discharge Losses (MW)'].sum()
                ],
                'Units': ['€', 'MWh', 'MWh', 'MWh', 'MWh', 'MWh', 'MWh', 'MWh', 'MWh']
            })

            # Format numeric columns
            # First round all numeric columns to 3 decimals
            numeric_cols = summary.select_dtypes(include='number').columns
            summary[numeric_cols] = summary[numeric_cols].round(3)
            
            # Then specifically round Total Operational Cost to 2 decimals
            summary.loc[summary['Metric'] == 'Total Operational Cost', 'Value'] = \
                summary.loc[summary['Metric'] == 'Total Operational Cost', 'Value'].round(2)

            summary.to_excel(writer, sheet_name='Sumário', startrow=6, index=False)
        
        print("Results saved to " + output_filename)
        
    else:
        print("Optimization failed, no results to save")

    # plot_figures(output_filename, 'Velocidade dos ventos.xlsx')

output_filename = 'Teste.xlsx'

main(output_filename, 10)