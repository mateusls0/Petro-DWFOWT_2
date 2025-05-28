import cdsapi
from grib_to_csv import grib_to_csv

def get_wind_data(variables, years, area_coordinates, csv_filename, grib_filename="data.grib", months=["01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12"],days=["01", "02", "03","04", "05", "06","07", "08", "09","10", "11", "12", "16", "17", "18","19", "20", "21","22", "23", "24","25", "26", "27","28", "29", "30","31"], to_samir=False):

    # Initiate client
    client = cdsapi.Client()

    # Indicate which dataset to pull from - always "reanalysis-era5-single-levels"
    dataset = "reanalysis-era5-single-levels"

    # Configure request parameters
    request = {
        "product_type": ["reanalysis"],

        # Possible to include other data as well - see https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels?tab=download
#                                                      https://confluence.ecmwf.int/display/CKB/ERA5%3A+data+documentation#heading-Parameterlistings
        "variable": variables,

        # List of years - years are available from 1940 to 2025
        "year": years,

        # All months
        "month": months,

        # All days
        "day": days,

        # All times
        "time": [
            "00:00", "01:00", "02:00",
            "03:00", "04:00", "05:00",
            "06:00", "07:00", "08:00",
            "09:00", "10:00", "11:00",
            "12:00", "13:00", "14:00",
            "15:00", "16:00", "17:00",
            "18:00", "19:00", "20:00",
            "21:00", "22:00", "23:00"
        ],
        # Always keep data format as .grib
        "data_format": "grib",
        # Download as raw file instead of zip file
        "download_format": "unarchived",
        # Area coordinates - [N, -W, -S, E] - unit 00.00° (just use numbers like 00.00)
        "area": area_coordinates
    }

    # Save pulled GRIB data
    target = grib_filename
    client.retrieve(dataset, request, target)

    # Convert GRIB to CSV
    grib_to_csv(grib_filename, csv_filename, to_samir)