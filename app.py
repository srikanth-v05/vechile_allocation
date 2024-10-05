from flask import Flask, render_template, request, jsonify
import pandas as pd
import ast
import requests
from geopy.distance import geodesic
import googlemaps
import time
import os
import folium
import polyline

app = Flask(__name__)

# Ensure the directory for maps exists
if not os.path.exists('static/vehicle_maps'):
    os.makedirs('static/vehicle_maps')

# Google Maps API Key
API_KEY = 'yoir_api_key' # Replace with your actual API key
gmaps = googlemaps.Client(key=API_KEY)

# Function to get coordinates for a district using Google Maps API
def get_coordinates(district_name):
    url = f"https://maps.googleapis.com/maps/api/geocode/json?address={district_name}&key={API_KEY}"
    response = requests.get(url)
    if response.status_code == 200:
        results = response.json().get('results')
        if results:
            location = results[0]['geometry']['location']
            return location['lat'], location['lng']
    return None

# Function to create a map for a vehicle
def create_vehicle_map(vehicle_name, checkpoints, district_coordinates):
    start_point = "No.35, Third Floor, Apoorva Louis Apartment, Reddiarpalayam, Puducherry, 605010"
    end_point = "WQM6+XWX Kurumbapet Dumpyard, VIP's Residential Area, Marie Oulgaret, Puducherry, 605111"
    
    waypoints = '|'.join(checkpoints)
    directions_url = f"https://maps.googleapis.com/maps/api/directions/json?origin={start_point}&destination={end_point}&waypoints={waypoints}&key={API_KEY}"
    response = requests.get(directions_url)
    
    if response.status_code == 200:
        polyline_points = response.json().get('routes')[0]['overview_polyline']['points']
        decoded_points = polyline.decode(polyline_points)
        
        start_coords = get_coordinates("Reddiarpalayam, Puducherry")
        m = folium.Map(location=start_coords, zoom_start=13)
        
        folium.PolyLine(decoded_points, color="blue", weight=2.5, opacity=1).add_to(m)
        folium.Marker(start_coords, tooltip="Start", icon=folium.Icon(color="green")).add_to(m)
        for checkpoint in checkpoints:
            folium.Marker(district_coordinates[checkpoint], tooltip=checkpoint).add_to(m)
        
        end_coords = get_coordinates("Kurumbapet Dumpyard, Puducherry")
        folium.Marker(end_coords, tooltip="End", icon=folium.Icon(color="red")).add_to(m)

        map_filename = os.path.join('static', 'vehicle_maps', f"{vehicle_name}_map.html")
        m.save(map_filename)
        print(f"Map for {vehicle_name} saved as {map_filename}")
        return map_filename

# Load district names from location.txt and fetch coordinates
def load_districts(file_path):
    with open(file_path, 'r') as file:
        districts = ast.literal_eval(file.read().strip())
    
    district_coordinates = {}
    for district in districts:
        coords = get_coordinates(district)
        if coords:
            district_coordinates[district] = coords
        else:
            print(f"Could not fetch coordinates for {district}.")
        time.sleep(1)  # To avoid hitting the API rate limit

    return districts, district_coordinates

# Load bin data from a CSV file
def load_bin_data(file_path):
    return pd.read_csv(file_path)

# Function to calculate weights for each district based on the selected date
def calculate_weights(bin_data, districts, selected_date):
    weights = {}
    filtered_data = bin_data[bin_data['Timestamp'].str.startswith(selected_date)]

    for district in districts:
        total_weight = filtered_data[filtered_data['Location'] == district]['Weight (kg)'].sum()
        weights[district] = total_weight

    return weights

# Function to calculate the distance between two districts
def calculate_distance(district1, district2, district_coordinates):
    coords1 = district_coordinates[district1]
    coords2 = district_coordinates[district2]
    return geodesic(coords1, coords2).km

# Function to create clusters using DFS
def create_clusters_with_dfs(districts, district_coordinates, max_distance=5, max_stops=2):
    clusters = []
    visited = set()

    # DFS Stack - start with the first district
    for district in districts:
        if district not in visited:
            stack = [district]  # Initialize DFS stack
            cluster = []

            # Perform DFS to find nearby districts
            while stack and len(cluster) < max_stops:
                current_district = stack.pop()
                if current_district not in visited:
                    cluster.append(current_district)
                    visited.add(current_district)

                    # Look for neighbors under the distance limit
                    for neighbor in districts:
                        if neighbor not in visited and len(cluster) < max_stops:
                            distance = calculate_distance(current_district, neighbor, district_coordinates)
                            if distance <= max_distance:
                                stack.append(neighbor)

            # Add the formed cluster if it has members
            if cluster:
                clusters.append(cluster)

    return clusters

# Function to allocate vehicles based on clusters
def allocate_vehicles(clusters):
    vehicle_allocations = {}
    total_vehicle_count = 0

    for cluster in clusters:
        vehicle_allocations[f"Vehicle {total_vehicle_count + 1}"] = cluster
        total_vehicle_count += 1

    return vehicle_allocations

@app.route('/')
def index():
    return render_template('index4.html')

@app.route('/run_allocation', methods=['POST'])
def run_allocation():
    try:
        selected_date = request.form.get('selected_date')
        if not selected_date:
            return jsonify({"error": "No date provided"}), 400

        # Load data
        districts, district_coordinates = load_districts('data/location.txt')
        bin_data = load_bin_data('data/garbage_data_check2.csv')

        # Calculate weights
        weights = calculate_weights(bin_data, districts, selected_date)

        # Create clusters with 2 stops max
        clusters = create_clusters_with_dfs(districts, district_coordinates)

        # Allocate vehicles using clusters
        vehicle_allocations = allocate_vehicles(clusters)

        # Prepare data for frontend
        vehicles_data = []
        for vehicle, allocated_districts in vehicle_allocations.items():
            # Generate the map
            map_filename = create_vehicle_map(vehicle, allocated_districts, district_coordinates)

            vehicles_data.append({
                "vehicle_id": vehicle,
                "assigned_districts": allocated_districts,
                "map_url": map_filename  # Include map URL in the response
            })

        return jsonify(vehicles_data)
    
    except Exception as e:
        print(f"Error during allocation: {e}")
        return jsonify({"error": "An error occurred during allocation."}), 500

if __name__ == '__main__':
    app.run(debug=True)
