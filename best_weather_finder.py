import requests
import folium
import streamlit as st
import re
from geopy.distance import geodesic
from datetime import datetime, timezone
from streamlit_folium import folium_static
from typing import Optional, Tuple

def parse_population(population_data: str) -> int:

    match = re.search(r'\d[\d\s]*', population_data)
    if match:
        cleaned_population_str = match.group().replace(' ', '')
        population = int(cleaned_population_str)
    else:
        population = 0 
    return population


# Function to get towns within a radius
def get_towns_within_radius(center_lat, center_lon, radius_km, min_population=500):
    overpass_url = "http://overpass-api.de/api/interpreter"
    overpass_query = f"""
    [out:json];
    (
      node["place"="city"](around:{radius_km * 1000},{center_lat},{center_lon})["population"];
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
            population = parse_population(element['tags']['population'])
            if population > min_population:
                town = (element['tags']['name'], element['lat'], element['lon'])
                towns.append(town)
                
    return towns


# Function to get weather data for multiple towns
def get_weather_data_for_towns(towns, api_key):
    weather_data_list = []
    status_text = st.empty()
    status_text.write('Fetching weather data...')
    progress_bar = st.progress(0)

    for index, town in enumerate(towns):
        lat, lon = town[1], town[2]
        url = f"http://api.openweathermap.org/data/2.5/forecast?lat={lat}&lon={lon}&appid={api_key}&units=metric"
        response = requests.get(url).json()
        weather_data_list.append((town[0], response))

        progress_percentage = int((index + 1) / len(towns) * 100)
        progress_bar.progress(progress_percentage)

    progress_bar.empty()
    status_text.empty()

    return weather_data_list


# Function to calculate weather score
def calculate_weather_score(weather_data, weights) -> float:
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
        

def get_user_coordinates(location) -> Optional[Tuple[float, float]]:
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
        return found_location
    else:
        print(f"Could not find coordinates for {location}. Please make sure the location is spelled correctly.")
        return None, None


def calculate_weather_scores_and_max(weather_data_list, weights) -> Tuple[list, float]:
    weather_scores = []
    max_score = 0
    for town, weather in weather_data_list:
        score = calculate_weather_score(weather, weights)
        if score > max_score:
            max_score = score
        weather_scores.append((town, weather, score))

    return weather_scores, max_score


def display_on_map(weather_scores, max_score, center_lat, center_lon, radius_km):
        # Visualize on a map
    map_center = [center_lat, center_lon]
    mymap = folium.Map(location=map_center, zoom_start = 9)
    
    for weather_score in weather_scores:
        if weather_score[2] == max_score:
            folium.Marker(
                location=[weather_score[1]['city']['coord']['lat'], weather_score[1]['city']['coord']['lon']],
                popup=f"{weather_score[0]}: {weather_score[2]:.2f}",
                icon=folium.Icon(color='green')  
            ).add_to(mymap)
        else:
            folium.Marker(
                location=[weather_score[1]['city']['coord']['lat'], weather_score[1]['city']['coord']['lon']],
                popup=f"{weather_score[0]}: {weather_score[2]:.2f}"
            ).add_to(mymap)

    return mymap


def find_best_weather(user_location, user_radius, user_population):
    #! Insert your OpenWeatherMap API key here. Create account, activate via email link, API key will be emailed to you.
    api_key = '88d3e456f87cc1e050630459f9c1a301'
    user_town = get_user_coordinates(user_location)
    user_lat = user_town['lat']
    user_lon = user_town['lon']
    
    weather_map = None
    if user_lat is None or user_lon is None:
        return False, True, weather_map
    else:
        coordinates_found = True
    
    weights = {'temp': 0.5, 'wind': 0.3, 'rain': 0.2}

    towns = get_towns_within_radius(user_lat, user_lon, user_radius, user_population)
    towns.append((user_location, user_lat, user_lon))   

    if(len(towns) == 0):
        return True, False, weather_map
    else: 
        towns_found = True
    
    weather_data_list = get_weather_data_for_towns(towns, api_key)
    weather_scores, max_score = calculate_weather_scores_and_max(weather_data_list, weights)
    weather_map = display_on_map(weather_scores, max_score, user_lat, user_lon, user_radius)

    return coordinates_found, towns_found, weather_map

if __name__ == "__main__":
    st.title('Best Weather Finder')
    st.subheader('Your solution to summer, wherever and whenever!')
    user_location = st.text_input('Where are you traveling from? e.g. New York')
    
    user_location = user_location.title()
    user_radius = st.slider('How far are you willing to travel?', 0, 100, 5)
    user_population = st.slider('Minimum population of town?', 0, 1000000, 500)
    if st.button('Find Best Weather!'):
        if not user_location.strip(): # Handle empty input
            st.error('Please enter a valid location.')
            st.stop()

        status_text = st.empty()
        status_text.write('Finding the best weather...')
        coordinates_found, towns_found, weather_map = find_best_weather(user_location, user_radius, user_population)
        status_text.empty()
        if not coordinates_found:
            st.write('Could not find coordinates for user location.')
            exit()
        if not towns_found:
            st.write('Could not find towns with enough population.')
            exit()

        folium_static(weather_map)

# TODO 3: Add more weather parameters to the calculation (e.g., humidity, cloudiness)
# TODO 5: Add error handling and logging
# TODO 6: Optimize the code for performance and readability
# TODO 7: Fine tune cost function
# TODO 8: Add Time of day and day you want to travel (use forecast)
# TODO 10: Add return and parameter types to functions
# TODO 12: Handle exceptions properly
# TODO 13: Make code more readable
# TODO 14: Make return values of get_user_location and get_towns_within_radius consistent