import requests
import folium
import streamlit as st
import re
import os
from datetime import datetime, timezone, timedelta
from streamlit_folium import folium_static
from typing import Optional, Tuple

import re

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
    try:
        response = requests.get(overpass_url, params={'data': overpass_query}, timeout=5)
    except requests.exceptions.Timeout:
        st.error("Searching for towns took too long. Please try again.")
        st.stop()
    data = response.json()
    towns = []
    for element in data['elements']:
        if 'tags' in element and 'population' in element['tags']:
            population = parse_population(element['tags']['population'])
            if population > min_population and 'name' in element['tags']:
                town = (element['tags']['name'], element['lat'], element['lon'])
                towns.append(town)
    return towns


# Function to get weather data for multiple towns
def get_weather_data_for_towns(towns: list[Tuple[str, float, float]], api_key: str) -> list[Tuple[str, dict]]:
    weather_data_list = []
    progress_bar = st.progress(0)

    for index, town in enumerate(towns):
        lat, lon = town[1], town[2]
        url = \
        f"http://api.openweathermap.org/data/2.5/forecast?lat={lat}&lon={lon}&appid={api_key}&units=metric"
        try:
            response = requests.get(url, timeout=5).json()
        except requests.exceptions.Timeout:
            st.error("Retrieving the weather data took too long. Please try again.")
            st.stop()
        weather_data_list.append((town[0], response))

        progress_percentage = int((index + 1) / len(towns) * 100)
        progress_bar.progress(progress_percentage)

    progress_bar.empty()

    return weather_data_list


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
    folium_static(mymap, width=650, height=400)


def select_homonymous_locations(locations) -> Optional[int]:
    options = ['']

    for i, _ in enumerate(locations):
        options.append(i)
    display_homonymous_location_map(locations)
    selected_option = \
    st.selectbox('Click on the location on the map and select the index here:', options)
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
    try:
        response = requests.get(overpass_url, params={'data': overpass_query}, timeout=5)
    except requests.exceptions.Timeout:
        st.error("Finding your location took too long. Please try again.")
        st.stop()
    data = response.json()
    return data


def calculate_weather_scores_and_max(weather_data_list: list[dict], weights: dict, user_days_ahead: int = 0) -> Tuple[list, float]:
    weather_scores_local = []
    max_score_local = 0
    for town, weather in weather_data_list:
        score = calculate_weather_score(weather, weights, user_days_ahead)
        if score > max_score_local:
            max_score_local = score
        weather_scores_local.append((town, weather, score))

    return weather_scores_local, max_score_local


def add_markers_to_weather_map(weather_scores_arg: list[dict], max_score_arg: float, mymap: folium.Map) -> None:
    for weather_score in weather_scores_arg:
        if weather_score[2] == max_score_arg:
            folium.Marker(
                location=[weather_score[1]['city']['coord']['lat'],
                          weather_score[1]['city']['coord']['lon']],
                          popup=f"{weather_score[0]}: {weather_score[2]:.2f}",
                icon=folium.Icon(color='green')
            ).add_to(mymap)


def display_best_weather_map(weather_scores_arg: list[dict], max_score_arg: float) -> None:
    map_center = [st.session_state['user_lat'], st.session_state['user_lon']]
    mymap = folium.Map(location=map_center, zoom_start = 9)
    add_markers_to_weather_map(weather_scores_arg, max_score_arg, mymap)
    folium_static(mymap)


def display_score_calculation_explanation() -> None:
    try:
        with open('weather_score_explanation.md', 'r', encoding='utf-8') as explanation_file:
            weather_score_explanation = explanation_file.read()
        st.markdown(weather_score_explanation)
    except FileNotFoundError:
        st.error("Error: The file 'weather_score_explanation.md' was not found.")
    except IOError:
        st.error("Error: An error occurred while reading the file 'weather_score_explanation.md'.")


def get_weather_preferences_from_ui() -> Tuple[float, float, float]:
    temp_pref        = st.sidebar.slider('Pleasant Temperature', min_value=0, 
                                         max_value=100, value=50)
    wind_speed_pref  = st.sidebar.slider('Low Wind Speeds', min_value=0, max_value=100, value=20)
    rainfall_pref    = st.sidebar.slider('Low Rainfall', min_value=0, max_value=100, value=30)
    weather_pref_sum = temp_pref + wind_speed_pref + rainfall_pref
    temp_pref       /= weather_pref_sum
    wind_speed_pref /= weather_pref_sum
    rainfall_pref   /= weather_pref_sum

    return temp_pref, wind_speed_pref, rainfall_pref
    

def get_location_preferences_from_ui() -> Tuple[int, int, int]:
    user_radius     = st.sidebar.slider('How far are you willing to travel?', 0, 100, 5)
    user_population = st.sidebar.slider('Minimum population of destination?', 0, 1000000, 500)
    user_days_ahead = st.sidebar.slider('In how many days are you planning to travel?', 0, 5, 0)
    
    return user_radius, user_population, user_days_ahead


def get_user_location_name_from_ui() -> str:
    user_location_name = st.text_input('Where do you need to escape from? e.g. New York')
    return user_location_name.strip().title()


def find_possible_user_locations(location_name: str) -> None:
    if not location_name.strip(): # Handle empty input
        st.error('Please enter a location.')
        st.stop()

    st.session_state['possible_user_locations'] = get_possible_user_locations(location_name)
    st.session_state['fetched_user_locations'] = True


def find_best_weather(user_preferences):

    api_key = os.getenv('API_KEY')

    if not api_key:
        st.error("API_KEY environment variable is not set.")
        st.stop()

    user_lat = st.session_state['user_lat']
    user_lon = st.session_state['user_lon']

    user_radius, user_population, user_days_ahead, temp_pref, wind_speed_pref, rainfall_pref \
        = user_preferences

    status_text = st.empty()
    sub_status_text = st.empty()
    status_text.write('Finding the best weather...')

    with st.spinner('Finding matching destinations, this will take a few seconds...'):
        towns = get_towns_within_radius(user_lat, user_lon, user_radius, user_population)

    if len(towns) == 0:
        sub_status_text.empty()
        st.info('Could not find towns with such a large population.\
                 Looks like staying at home is the best option!', icon="ℹ️")
        st.stop()

    sub_status_text.write('Fetching weather data...')
    weather_data_list = get_weather_data_for_towns(towns, api_key)
    sub_status_text.empty()

    weights = {'temp': temp_pref, 'wind': wind_speed_pref, 'rain': rainfall_pref}

    status_text.empty()
    
    return calculate_weather_scores_and_max(weather_data_list, weights, user_days_ahead)


def determine_user_coordinates() -> None:

    possible_user_locations = st.session_state['possible_user_locations']
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
        st.error('Could not find coordinates for user location.')
        st.info('Note: If you cannot find your location, find out what it is called in \
                OpenStreetMap: https://www.openstreetmap.org/', icon='ℹ️')
        st.stop()

    st.session_state['user_lat'] = user_coordinates['lat']
    st.session_state['user_lon'] = user_coordinates['lon']


if __name__ == "__main__":

    ####################### Setup #######################

    st.set_page_config(page_title='Best Weather Finder', page_icon='🏖️', 
                       layout="wide", initial_sidebar_state="auto", menu_items=None)

    st.title('Best Weather Finder 🏖️')
    col1, col2 = st.columns(2)

    ####################### Preferences #######################

    st.sidebar.title("Preferences")
    st.sidebar.header("Weather 🌤️")
    weather_preferences = get_weather_preferences_from_ui()

    st.sidebar.info('0:   Not Important  \n100: Very Important', icon='ℹ️')

    st.sidebar.markdown("---")
    st.sidebar.header("Travel 🧳")

    location_preferences = get_location_preferences_from_ui()

    ####################### Finding Location #######################

    with col1:
        user_location = get_user_location_name_from_ui()
        # If there are multiple locations with the same name, this part of the script 
        # must be executed again to determine the coordinates of the selected location
        if st.button('Find My Location'):
            find_possible_user_locations(user_location)

        if 'fetched_user_locations' in st.session_state and \
            st.session_state['fetched_user_locations'] is True:
            determine_user_coordinates()

        if 'fetched_user_locations' not in st.session_state:
            st.stop()

        st.success('Found your location!', icon="✅")

    ####################### Finding Best Weather #######################

        if st.button('Find Best Weather!'):
            with col2:
                weather_scores, max_score = \
                    find_best_weather(location_preferences + weather_preferences)
                display_best_weather_map(weather_scores, max_score)

                st.session_state['multiple_user_locations'] = None
                with st.expander('How is the weather score calculated?'):
                    display_score_calculation_explanation()
