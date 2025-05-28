import csv
from datetime import datetime
from eccodes import *

def grib_to_csv(grib_file, csv_file, to_samir=False):

    # Dictionary to store data in the new format
    data = {}

    # Open GRIB file
    with open(grib_file, "rb") as f:
        while True:
            try:
                gid = codes_grib_new_from_file(f)
                if gid is None:
                    break

                # Get metadata
                date = str(codes_get(gid, "date"))  # YYYYMMDD
                time = str(codes_get(gid, "time")).zfill(4)  # HHMM, zero-padded
                var_name = codes_get(gid, "shortName")  # Variable name (e.g., 100u, 100v)

                # Convert date & time to DD-MM-YYYY HH:MM format
                dt = datetime.strptime(date + time, "%Y%m%d%H%M").strftime("%d-%m-%Y %H:%M")

                # Get latitudes, longitudes, and values
                lats = codes_get_array(gid, "latitudes")
                lons = codes_get_array(gid, "longitudes")
                values = codes_get_array(gid, "values")

                # Store data in dictionary
                for lat, lon, val in zip(lats, lons, values):
                    key = (dt, lat, lon)  # Primary key
                    if key not in data:
                        data[key] = {"datetime": dt, "latitude": lat, "longitude": lon}
                    
                    data[key][var_name] = val  # Assign value to the correct variable column

                # Release GRIB message
                codes_release(gid)

            except CodesInternalError as e:
                print(f"GRIB decoding error: {e}")
                break

    # Get all variable names dynamically
    variable_names = set(var for entry in data.values() for var in entry.keys() if var not in ["datetime", "latitude", "longitude"])

    # Write to CSV

    if not to_samir:
        with open(csv_file, mode="w", newline="") as csv_f:
            writer = csv.writer(csv_f)

            # Define header dynamically
            headers = ["datetime", "latitude", "longitude"] + sorted(variable_names)
            writer.writerow(headers)

            # Write rows
            for key, values in data.items():
                row = [values.get(col, "") for col in headers]  # Get value or empty if missing
                writer.writerow(row)

    else:
        with open(csv_file, mode="w", newline="") as csv_f:
            # Set delimiter to ';'
            writer = csv.writer(csv_f, delimiter=';')

            # Define header dynamically
            headers = ["datetime", "latitude", "longitude"] + sorted(variable_names)
            writer.writerow(headers)

            # Write rows
            for key, values in data.items():
                row = []
                for col in headers:
                    value = values.get(col, "")
                    # Replace decimal separator for floats
                    if isinstance(value, float):
                        value = str(value).replace('.', ',')
                    row.append(value)
                writer.writerow(row)


    print(f"CSV file saved as {csv_file}")