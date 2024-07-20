import requests
import folium
import streamlit as st
import re
import os
from dotenv import load_dotenv
from geopy.distance import geodesic
from datetime import datetime, timezone, timedelta
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


def parse_location(location_name: str) -> str:
    words = location_name.split()
    filtered_words = [word.rstrip(',') for word in words if ':' not in word]
    parsed_location = ' '.join(filtered_words)
    return parsed_location


# Function to get towns within a radius
def get_towns_within_radius(center_lat: float, center_lon: float, radius_km: int, min_population: int = 500) -> list[Tuple[str, float, float]]:
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
            population = parse_population(element['tags']['population'])
            if population > min_population:
                town = (element['tags']['name'], element['lat'], element['lon'])
                towns.append(town)
                
    return towns


# Function to get weather data for multiple towns
def get_weather_data_for_towns(towns: list[Tuple[str, float, float]], api_key: str) -> list[Tuple[str, dict]]:
    weather_data_list = []
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
def calculate_weather_score(weather_data: dict, weights: dict, user_days_ahead: int = 0) -> float:
    forecast_date = (datetime.now() + timedelta(days=user_days_ahead)).strftime('%Y-%m-%d')

    total_temp_value = 0
    total_wind_value = 0
    total_rain_value = 0
    count = 0

    for entry in weather_data['list']:
        dt = (datetime.fromtimestamp(entry['dt'], tz=timezone.utc)).strftime('%Y-%m-%d')
        if dt == forecast_date:
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
def calculate_value(temp: float, wind_speed: float, rain: float) -> Tuple[float, float, float]:
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


def display_homonymous_location_map(locations: list[dict]) -> folium.Map:
    # Visualize on a map
    mymap = folium.Map(zoom_start = 1)
    
    for index, location in enumerate(locations):
        folium.Marker(
            location=[location['lat'], location['lon']],
            popup=f"{index}",
            icon=folium.Icon(color='green')  
        ).add_to(mymap)

    return mymap


def select_homonymous_locations(locations):
    options = ['']

    for i, _ in enumerate(locations):
        options.append(i)
    
    homonymous_locations_map = display_homonymous_location_map(locations)
    folium_static(homonymous_locations_map)

    selected_option = st.selectbox('Click on the location on the map and select the index here:', options)
    if selected_option == '':
        return None

    selected_option_index = options.index(selected_option) - 1
    return selected_option_index
        

def get_possible_user_locations(location_name) -> dict:
    overpass_url = "http://overpass-api.de/api/interpreter"
    overpass_query = f"""
    [out:json];
    (
      node["place"="town"]["name"="{location_name}"];
      node["place"="village"]["name"="{location_name}"];
      node["place"="city"]["name"="{location_name}"];
    );
    out body;
    """
    response = requests.get(overpass_url, params={'data': overpass_query})
    data = response.json()
    return data


def calculate_weather_scores_and_max(weather_data_list: list[dict], weights: dict, user_days_ahead: int = 0) -> Tuple[list, float]:
    weather_scores = []
    max_score = 0
    for town, weather in weather_data_list:
        score = calculate_weather_score(weather, weights, user_days_ahead)
        if score > max_score:
            max_score = score
        weather_scores.append((town, weather, score))

    return weather_scores, max_score


def display_best_weather_map(weather_scores: list[dict], max_score: float, center_lat: float, center_lon: float) -> folium.Map:
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

if __name__ == "__main__":

    # Access the API key from the environment variables
    api_key = os.getenv('API_KEY')

    if not api_key:
        st.error("API_KEY environment variable is not set.")
    else:
        st.write(f"Your API Key is: {api_key}")

    st.title('Best Weather Finder 🏖️')
    st.subheader('Your solution to summer, wherever and whenever!')
    user_location_name = st.text_input('Where do you need to escape from? e.g. New York')
    user_location_name = user_location_name.title()
    user_coordinates = None
    user_lat = None
    user_lon = None 

    if st.button('Find My Location') or ('multiple_user_locations' in st.session_state and st.session_state['multiple_user_locations'] == True):             
        if not user_location_name.strip(): # Handle empty input
            st.error('Please enter a valid location.')
            st.stop()

        possible_user_locations = get_possible_user_locations(user_location_name)
        user_coordinates = None
        if len(possible_user_locations['elements']) > 1:
            st.write('Multiple locations found with the same name.')
            user_location_index = select_homonymous_locations(possible_user_locations['elements'])
            st.session_state['multiple_user_locations'] = True
            if user_location_index is None:
                st.stop()
            user_coordinates = possible_user_locations['elements'][user_location_index]
        elif len(possible_user_locations['elements']) == 1: 
            st.session_state['multiple_user_locations'] = False
            user_coordinates = possible_user_locations['elements'][0]
        else: 
            st.session_state['multiple_user_locations'] = False

        if user_coordinates is None:
            st.error('Could not find coordinates for user location.')
            st.info('Note: If you cannot find your location, find out what it is called in OpenStreetMap: https://www.openstreetmap.org/', icon='ℹ️')
            exit()
        
        
        
        user_lat = user_coordinates['lat']
        user_lon = user_coordinates['lon']
        st.session_state['user_lat'] = user_lat
        st.session_state['user_lon'] = user_lon

    # Don't display below if correct location is not selected
    if 'multiple_user_locations' not in st.session_state:
        st.stop()

    st.success('Found your location!', icon="✅")

    user_radius = st.slider('How far are you willing to travel?', 0, 100, 5)
    user_population = st.slider('Are you a city person (Minimum population of destination)?', 0, 1000000, 500)
    user_days_ahead = st.slider('In how many days are you planning to travel?', 0, 5, 0)
    user_lat = st.session_state['user_lat']
    user_lon = st.session_state['user_lon']

    if st.button('Find Best Weather!'):

        status_text = st.empty()
        status_text.write('Finding the best weather...')

        weights = {'temp': 0.5, 'wind': 0.3, 'rain': 0.2}

        status_text.write('Finding matching destinations, this will take a few seconds...')
        towns = get_towns_within_radius(user_lat, user_lon, user_radius, user_population)
        towns.append((user_location_name, user_lat, user_lon)) 
        if len(towns) == 1:
            st.write('Could not find towns with such a large population')
        
        #! Insert your OpenWeatherMap API key here. Create account, activate via email link, API key will be emailed to you. 
        status_text.write('Fetching weather data...') 
        weather_data_list = get_weather_data_for_towns(towns, api_key)
        status_text = st.empty()
        weather_scores, max_score = calculate_weather_scores_and_max(weather_data_list, weights, user_days_ahead)
        
        status_text.write('Here you go!')
        weather_map = display_best_weather_map(weather_scores, max_score, user_lat, user_lon)

        folium_static(weather_map)

        st.session_state.clear()

# TODO 1: Add explanation how the weather score is calculated
# TODO 2: Let user determine weights for weather parameters (maybe in side bar)
# TODO 3: Design
# TODO 4: Fine tune cost function