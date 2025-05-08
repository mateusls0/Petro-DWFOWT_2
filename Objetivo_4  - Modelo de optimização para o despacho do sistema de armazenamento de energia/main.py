import pypsa
import pandas as pd

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
        )['load [MW]'].sort_index()
        
        # Select first 10 time steps
        snapshots = wind_speed.index[:10]
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
network = pypsa.Network()
network.set_snapshots(snapshots)

# Add required carriers
network.add("Carrier", "Wind")
network.add("Carrier", "Battery")
network.add("Carrier", "AC")

# Create buses with AC carrier
network.add("Bus", "Node1", carrier="AC")
network.add("Bus", "Node2", carrier="AC")

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
        
        # Create temporary sorted DataFrame for merging
        wind_df = pd.DataFrame({'Wind Speed [m/s]': wind_speed})
        wind_sorted = wind_df.sort_values('Wind Speed [m/s]')
        
        # Merge with power curve using nearest lower value
        merged = pd.merge_asof(
            wind_sorted,
            power_curve,
            on='Wind Speed [m/s]',
            direction='backward'
        )
        
        # Restore original time order
        p_max_pu = merged.set_index(wind_speed.index)['Power [pu]']
        
        # Add generator to network
        network.add("Generator",
            "Wind Turbine",
            bus="Node1",
            carrier="Wind",
            p_nom=15,
            committable=True,
            p_min_pu=0,
            p_max_pu=p_max_pu,
            # min_up_time=3,
            # min_down_time=3,
            min_up_time=0,
            min_down_time=0,
            marginal_cost=10
        )
        
    except Exception as e:
        print(f"Wind turbine configuration failed: {e}")
        raise

create_wind_generator(network, wind_speed)

# ==============================
# 4. BATTERY STORAGE SETUP
# ==============================

battery_capacity = 4             # 4 MWh of capacity
battery_p_nom = 1                # 1 MW nominal power
battery_depth_of_discharge = 0.8 # 80% depth of discharge
battery_capacity *= battery_depth_of_discharge

network.add("StorageUnit",
    "Battery",
    bus="Node2",
    carrier="Battery",             
    p_nom=battery_p_nom,           
    max_hours=battery_capacity/battery_p_nom,
    efficiency_store=0.95,                        # Charging efficiency
    efficiency_dispatch=0.95,                     # Discharging efficiency
    standing_loss=0.005,                          # 0.5% hourly self-discharge
    state_of_charge_initial=battery_capacity,     # 100% initial SOC
    cyclic_state_of_charge=False,
    marginal_cost=1
)

# ==============================
# 5. CABLE CONNECTION SETUP
# ==============================

network.add("Link",
    "Cable",
    bus0="Node1",
    bus1="Node2",
    efficiency=0.98,   # 2% power loss
    p_nom=20,          # MW capacity
    p_min_pu=0         # Unidirectional power flow
)

# ==============================
# 6. LOAD CONFIGURATION
# ==============================

network.add("Load",
    "Water Injection",
    bus="Node2",
    p_set=load_profile
)

# ==============================
# 7. OPTIMIZATION SETUP
# ==============================

# Run optimization
network.optimize(
    solver_name='gurobi',
    solver_options={
        'Threads': 6,
        'MIPGap': 0.0001,
        'TimeLimit': 3000,
        'LogToConsole': 1
    }
)

# ==============================
# 8. RESULTS PROCESSING AND EXPORT
# ==============================

if network.model.status == "ok":
    # Create main results dataframe
    results = pd.DataFrame(index=snapshots)
    
    # Power values
    results['Wind Power (MW)'] = network.generators_t.p["Wind Turbine"]
    results['Cable Flow (MW)'] = network.links_t.p0["Cable"]
    results['Load (MW)'] = network.loads_t.p["Water Injection"]
    
    # Battery values
    results['Battery Charge (MW)'] = network.storage_units_t.p_store["Battery"]
    results['Battery Discharge (MW)'] = network.storage_units_t.p_dispatch["Battery"]
    results['State of Charge (MWh)'] = network.storage_units_t.state_of_charge["Battery"]
    
    # Loss calculations
    results['Cable Losses (MW)'] = abs(results['Cable Flow (MW)']) * 0.02
    
    # Split battery losses
    charging_loss = results['Battery Charge (MW)'] * (1 - 0.95)
    discharging_loss = results['Battery Discharge (MW)'] * (1/0.95 - 1)
    
    # Calculate self-discharge losses (standing losses)
    standing_loss = network.storage_units.standing_loss["Battery"]
    initial_soc = network.storage_units.state_of_charge_initial["Battery"]
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
    
    # Add total cost as final row
    total_cost = pd.DataFrame({
        'Total Operational Cost (€)': [network.objective],
        'Total Wind Cost (€)': [results['Wind Cost (€)'].sum()],
        'Total Battery Cost (€)': [results['Battery Cost (€)'].sum()],
        'Total Losses (MWh)': [results['Total Losses (MW)'].sum()],
    }, index=['Totals'])
    
    # Format numeric columns
    numeric_cols = results.select_dtypes(include='number').columns
    results[numeric_cols] = results[numeric_cols].round(3)
    
    # Create Excel writer and save
    with pd.ExcelWriter('Resultados otimizacao.xlsx') as writer:
        # Main results sheet
        results.to_excel(writer, sheet_name='Resultados completos')
        
        # Summary sheet
        total_cost.to_excel(writer, sheet_name='Sumário')
        
        # Create detailed summary
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
        summary.to_excel(writer, sheet_name='Sumário', startrow=6, index=False)
    
    print("Results saved to Resultados otimizacao.xlsx")
    
else:
    print("Optimization failed, no results to save")