"""
Interactive Wind Rose Map Generator
Creates an interactive map with wind roses showing wind patterns at different locations
"""

# Core dependencies
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from windrose import WindroseAxes
import folium
from io import BytesIO
import base64

def plot_interactive_map(csv_filename, plot_filename="wind_roses_map.html", to_samir=False):

    # ---------------------------
    # DATA PREPARATION SECTION
    # ---------------------------

    # Load wind data from CSV file
    if to_samir:
        df = pd.read_csv(csv_filename, sep=";", decimal=",")
    else:
        df = pd.read_csv(csv_filename)

    # Calculate wind parameters using vector components
    # wind_speed: Magnitude of wind vector (m/s)
    # wind_dir: Meteorological direction (0°=North, 90°=East)
    df["wind_speed"] = np.sqrt(df["100u"]**2 + df["100v"]**2)
    df["wind_dir"] = (90.0 - np.degrees(np.arctan2(df["100v"], df["100u"]))) % 360
    

    # ---------------------------
    # MAP CONFIGURATION
    # ---------------------------

    # Create base map using CartoDB Positron tiles (light land, blue water)
    map_center = [df.latitude.mean(), df.longitude.mean()]
    m = folium.Map(location=map_center, 
                tiles="CartoDB Positron", 
                zoom_start=6)

    # ---------------------------
    # COORDINATE FORMATTING FUNCTION
    # ---------------------------

    def format_coord(coord, is_latitude=True):
        """
        Convert decimal coordinate to directional notation
        Args:
            coord: Decimal coordinate value
            is_latitude: True for latitude, False for longitude
        Returns:
            Formatted string (e.g., "23.50° S")
        """
        direction = 'N' if is_latitude else 'E'
        if coord < 0:
            direction = 'S' if is_latitude else 'W'
        return f"{abs(coord):.2f}° {direction}"

    # ---------------------------
    # WIND ROSE GENERATION FUNCTION
    # ---------------------------

    def create_wind_rose_image(data, simplified=True):
        """
        Generate wind rose plot image in PNG format
        Args:
            data: DataFrame with wind_dir and wind_speed columns
            simplified: True for map markers, False for detailed popups
        Returns:
            Base64 encoded PNG image
        """
        # Configure plot dimensions and resolution
        figsize = (2, 2) if simplified else (6, 6)
        dpi = 50 if simplified else 100
        nsector = 8 if simplified else 16  # Number of directional sectors
        bins = np.arange(0, 21, 5)  # Wind speed bins (0-20 m/s in 5 m/s steps)
        cmap = plt.cm.viridis  # Color map for speed ranges

        # Create figure with transparent background
        fig = plt.figure(figsize=figsize, dpi=dpi, facecolor='none')
        ax = WindroseAxes.from_ax(fig=fig)
        
        # Create wind rose bars with white edges between sectors
        ax.bar(data.wind_dir, data.wind_speed, 
            bins=bins, 
            nsector=nsector,
            cmap=cmap,
            edgecolor="white",
            opening=0.8)
        
        ax.set_yticklabels([])  # Remove radial labels

        if simplified:
            # Simplified version for map markers
            ax.set_axisbelow(True)
            ax.grid(True, color='gray', linestyle='--', alpha=0.7)  # Add gridlines
            ax.set_xticklabels([])  # Remove direction labels
            ax.set_legend().set_visible(False)  # Hide legend
        else:
            # Detailed version for popups
            # Set high contrast labels
            for text in ax.get_children():
                if isinstance(text, plt.Text):
                    text.set_color('black')
                    text.set_backgroundcolor('white')
                    text.set_alpha(0.8)

            # Create legend with dark background
            legend = ax.set_legend(
                title="Speed (m/s)", 
                loc="lower left",
                facecolor='#333333',  # Dark gray background
                edgecolor='white',    # White border
                title_fontproperties={'weight': 'bold', 'size': 10},
                prop={'size': 9}
            )
            
            # Manual color override for legend text (workaround for library limitation)
            legend.get_title().set_color('white')
            for text in legend.get_texts():
                text.set_color('white')

        # Convert plot to base64 encoded PNG
        img_buffer = BytesIO()
        plt.savefig(img_buffer, format="png", bbox_inches='tight', pad_inches=0, transparent=True)
        plt.close()
        return base64.b64encode(img_buffer.getvalue()).decode("utf-8")

    # ---------------------------
    # MAP MARKER GENERATION
    # ---------------------------

    # Process each unique location in the dataset
    for (lat, lon), group in df.groupby(["latitude", "longitude"]):
        # Generate wind rose images
        simple_img = create_wind_rose_image(group, True)  # Small marker version
        detailed_img = create_wind_rose_image(group, False)  # Detailed popup version
        
        # Create custom map marker with wind rose image
        icon = folium.features.CustomIcon(
            f"data:image/png;base64,{simple_img}",
            icon_size=(40, 40),  # Marker size in pixels
            icon_anchor=(20, 20)  # Anchor point at center
        )
        
        # Create popup content with coordinates and detailed wind rose
        popup_html = f'''
        <div style="font-family: Arial; font-size: 14px; margin-bottom: 10px;">
            Latitude: {format_coord(lat, True)}<br>
            Longitude: {format_coord(lon, False)}
        </div>
        <img src="data:image/png;base64,{detailed_img}" width=400>
        '''
        
        # Add marker to map
        folium.Marker(
            location=[lat, lon],
            icon=icon,
            popup=folium.Popup(popup_html, max_width=420)
        ).add_to(m)

    # ---------------------------
    # DATA ANALYSIS FOR METADATA
    # ---------------------------

    # Convert datetime strings to datetime objects
    df['datetime'] = pd.to_datetime(df['datetime'], format='%d-%m-%Y %H:%M')

    # Get first and last timestamps
    first_timestamp = df['datetime'].min()
    last_timestamp = df['datetime'].max()

    # Calculate time intervals between consecutive measurements
    interval_str = "1 hour"

    # Calculate grid resolution
    lat_resolution = 0.25
    lon_resolution = 0.25

    # Format resolution string
    if lat_resolution == lon_resolution:
        resolution_str = f"{lat_resolution:.2f}°"
    else:
        resolution_str = f"{lat_resolution:.2f}° for latitudes and {lon_resolution:.2f}° for longitudes"

    # ---------------------------
    # INFORMATION BOX
    # ---------------------------

    # Create HTML/CSS for the information box
    info_html = f"""
    <div style="
        position: fixed; 
        bottom: 20px; 
        right: 10px;
        z-index: 1000;
        background-color: rgba(255, 255, 255, 0.9);
        padding: 15px 25px;
        border-radius: 8px;
        box-shadow: 0 3px 6px rgba(0,0,0,0.16);
        font-family: Arial, sans-serif;
        text-align: left;
        max-width: 330px;
    ">
        <div style="
            font-size: 14px;
            color: #34495e;
            line-height: 1.5;
        ">
            <div>From {first_timestamp.strftime('%d/%m/%Y %H:%M')} to {last_timestamp.strftime('%d/%m/%Y %H:%M')}</div>
            <div>Data acquired every {interval_str}</div>
            <div>Grid resolution of {resolution_str}</div>
        </div>
    </div>
    """

    # Add information box to the map
    m.get_root().html.add_child(folium.Element(info_html))

    # ---------------------------
    # WIND SPEED LEGEND
    # ---------------------------

    # Create HTML/CSS for the fixed legend
    legend_html = """
    <div style="
        position: fixed; 
        top: 10px; 
        right: 10px; 
        z-index: 1000;
        background-color: rgba(255, 255, 255, 0.8);
        padding: 10px;
        border-radius: 5px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.2);
        font-family: Arial, sans-serif;
    ">
        <div style="font-weight: bold; margin-bottom: 5px;">Wind Speed (m/s)</div>
        <div style="display: grid; grid-template-columns: 20px auto; gap: 5px; align-items: center;">
            <div style="background-color: #440154; height: 15px; width: 15px;"></div>
            <div>0 - 5</div>
            <div style="background-color: #3b528b; height: 15px; width: 15px;"></div>
            <div>5 - 10</div>
            <div style="background-color: #21918c; height: 15px; width: 15px;"></div>
            <div>10 - 15</div>
            <div style="background-color: #5ec962; height: 15px; width: 15px;"></div>
            <div>15 - 20</div>
            <div style="background-color: #fde725; height: 15px; width: 15px;"></div>
            <div>20+</div>
        </div>
    </div>
    """

    # Add legend to the map
    m.get_root().html.add_child(folium.Element(legend_html))

    # ---------------------------
    # SAVE AND OUTPUT
    # ---------------------------

    # Save interactive map as HTML file
    m.save(plot_filename)

    print("Map generation complete! Open wind_rose_interactive.html in a web browser.")

plot_interactive_map("data_analysis_samir.csv", to_samir=True)