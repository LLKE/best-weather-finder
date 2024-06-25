import requests
import folium
from geopy.distance import geodesic
from datetime import datetime, timezone
import streamlit as st

# Function to get towns within a radius
def get_towns_within_radius(center_lat, center_lon, radius_km, min_population=500):
    overpass_url = "http://overpass-api.de/api/interpreter"
    overpass_query = f"""
    [out:json];
    (
      node["place"="town"](around:{radius_km * 1000},{center_lat},{center_lon})["population"];
      node["place"="village"](around:{radius_km * 1000},{center_lat},{center_lon})["population"];
    );
    out body;
    """
    response = requests.get(overpass_url, params={'data': overpass_query})
    data = response.json()

    towns = []
    for element in data['elements']:
        if 'tags' in element and 'population' in element['tags']:
            #! Population may contain letters as well!
            population = int(element['tags']['population'])
            if population > min_population:
                town = (element['tags']['name'], element['lat'], element['lon'])
                towns.append(town)
                
    return towns

# Function to get weather data for multiple towns
def get_weather_data_for_towns(towns, api_key):
    weather_data = []
    for town in towns:
        lat, lon = town[1], town[2]
        url = f"http://api.openweathermap.org/data/2.5/forecast?lat={lat}&lon={lon}&appid={api_key}&units=metric"
        response = requests.get(url).json()
        weather_data.append((town[0], response))
    return weather_data

# Function to calculate weather score
def calculate_weather_score(weather_data, weights):
    sunrise = datetime.fromtimestamp(weather_data['city']['sunrise'], tz=timezone.utc)
    sunset = datetime.fromtimestamp(weather_data['city']['sunset'], tz=timezone.utc)

    total_temp_value = 0
    total_wind_value = 0
    total_rain_value = 0
    count = 0

    for entry in weather_data['list']:
        dt = datetime.fromtimestamp(entry['dt'], tz=timezone.utc)
        if sunrise <= dt <= sunset:
            temp = entry['main']['temp']
            wind_speed = entry['wind']['speed']
            rain = entry['rain'].get('3h', 0) if 'rain' in entry else 0

            temp_value, wind_value, rain_value = calculate_value(temp, wind_speed, rain)
            total_temp_value += temp_value
            total_wind_value += wind_value
            total_rain_value += rain_value
            count += 1

    if count == 0:
        return 0  # No data within the defined hours

    # Normalize
    norm_temp_value = total_temp_value / count
    norm_wind_value = total_wind_value / count
    norm_rain_value = total_rain_value / count

    # Weighted sum
    total_score = (weights['temp'] * norm_temp_value +
                   weights['wind'] * norm_wind_value +
                   weights['rain'] * norm_rain_value)

    # Normalize to 0-1 range
    total_score /= sum(weights.values())

    return total_score

# Function to calculate value based on temp, wind, rain
def calculate_value(temp, wind_speed, rain):
    if temp > 25:
        temp_value = 1
    elif 20 <= temp <= 25:
        temp_value = 0.5
    else:
        temp_value = 0

    if wind_speed < 5:
        wind_value = 1
    elif 5 <= wind_speed < 10:
        wind_value = 0.5
    else:
        wind_value = 0

    if rain == 0:
        rain_value = 1
    elif rain < 5:
        rain_value = 0.5
    else:
        rain_value = 0

    return temp_value, wind_value, rain_value


def select_homonymous_locations(locations):
    print(f"Found multiple locations with the same name. Please select one:")
    options = []
    for i, location in enumerate(locations):
        options[i] = location['tags']['name']
    selected_option = st.selectbox('Select the correct location:', options)
    return selected_option
        

def get_user_coordinates(location):
    overpass_url = "http://overpass-api.de/api/interpreter"
    overpass_query = f"""
    [out:json];
    (
      node["place"="town"]["name"="{location}"];
      node["place"="village"]["name"="{location}"];
      node["place"="city"]["name"="{location}"];
    );
    out body;
    """
    response = requests.get(overpass_url, params={'data': overpass_query})
    data = response.json()

    if len(data['elements']) >= 1:
        found_location = data['elements'][0]
        print(f"Found coordinates for {location}: {found_location['lat']}, {found_location['lon']}")
        return found_location['lat'], found_location['lon']
    else:
        print(f"Could not find coordinates for {location}. Please make sure the location is spelled correctly.")
        return None, None


def find_best_weather(user_location, user_radius, user_population):
    #! Insert your OpenWeatherMap API key here. Create account, activate via email link, API key will be emailed to you.
    api_key = '88d3e456f87cc1e050630459f9c1a301'
    center_lat, center_lon = get_user_coordinates(user_location)  # Example coordinates for Aachen, Germany
    
    if center_lat is None or center_lon is None:
        return False
    else:
        coordinates_found = True
    
    weights = {'temp': 0.5, 'wind': 0.3, 'rain': 0.2}

    towns = get_towns_within_radius(center_lat, center_lon, user_radius, user_population)
    weather_data_list = get_weather_data_for_towns(towns, api_key)

    # Calculate and print weather scores for each town
    for town_name, weather_data in weather_data_list:
        score = calculate_weather_score(weather_data, weights)
        print(f"Total weather score for {town_name}: {score}")

    # Visualize on a map
    map_center = [center_lat, center_lon]
    mymap = folium.Map(location=map_center, zoom_start=10)

    for town_name, weather_data in weather_data_list:
        score = calculate_weather_score(weather_data, weights)
        folium.Marker(
            location=[weather_data['city']['coord']['lat'], weather_data['city']['coord']['lon']],
            popup=f"{town_name}: {score:.2f}"
        ).add_to(mymap)

    mymap.save('weather_scores_map.html')
    print('Map saved as weather_scores_map.html')

    return coordinates_found

# Main code 

st.title('Best Weather Finder')
st.subheader('Your solution to summer, wherever and whenever!')
user_location = st.text_input('Where are you traveling from?')
user_radius = st.slider('How far are you willing to travel?', 0, 100, 5)
user_population = st.slider('Minimum population of town?', 0, 1000000, 500)
if st.button('Find Best Weather!'):
    st.write('Finding the best weather...')
    st.write('This may take a few seconds...')
    coordinates_found = find_best_weather(user_location, user_radius, user_population)
    if not coordinates_found:
        st.write('Could not find coordinates for user location. Exiting...')
    elif coordinates_found:
        st.write('Found coordinates for user location!')

    

# TODO 1: Add a function to get the best town based on weather score
# TODO 2: Display weather scores on the map and color code the markers based on the score
# TODO 3: Add more weather parameters to the calculation (e.g., humidity, cloudiness)
# TODO 4: Improve the user interface to input location and preferences (wrap in streamlit)
# TODO 5: Add error handling and logging
# TODO 6: Optimize the code for performance and readability
# TODO 7: Fine tune cost function
# TODO 8: Add Time of day you want to travel