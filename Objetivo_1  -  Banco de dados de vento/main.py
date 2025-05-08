from get_data_grib import get_wind_data
from plot_map import plot_interactive_map

def main():

    # Possible to include other data as well - see https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels?tab=download
    #                                              https://confluence.ecmwf.int/display/CKB/ERA5%3A+data+documentation#heading-Parameterlistings
    variables = ["100m_u_component_of_wind",
                "100m_v_component_of_wind"]

    # List of years - years are available from 1940 to 2025
    years = ["2024"]

    # List of months - optional - default: all months
    months = ["02"]

    # List of days - optional - default: all days
    days = ["11"]

    # Area coordinates - [N, -W, -S, E] - unit 00.00° (just use numbers like 00.00)
    area_coordinates = [-22.74, -41.9, -22.82, -41.8]

    # Raw GRIB data file - optional - default: data.grib
    grib_filename = 'data_analysis_samir.grib'

    # Output CSV file
    csv_filename = 'data_analysis_samir.csv'

    get_wind_data(variables, years, area_coordinates, csv_filename, grib_filename=grib_filename, to_samir=True)
    plot_interactive_map(csv_filename, to_samir=True)

main()