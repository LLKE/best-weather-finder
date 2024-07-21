## Weather Score Calculation Explained

1. **Data Aggregation**: For the selected date, the system aggregates weather data including temperature, wind speed, and rainfall from Open Weather Map forecast data.

2. **Value Calculation**:
- **Temperature**: A value is assigned based on the temperature:
    - Above 25°C: High preference.
    - Between 20°C and 25°C: Moderate preference.
    - Below 20°C: Low preference.
- **Wind Speed**: A value is assigned based on wind speed:
    - Below 5 km/h: High preference.
    - Between 5 km/h and 10 km/h: Moderate preference.
    - Above 10 km/h: Low preference.
- **Rainfall**: A value is assigned based on rainfall:
    - No rain: High preference.
    - Below 5 mm: Moderate preference (score of 0.5).
    - Above 5 mm: Low preference (score of 0).

3. **Normalization and Weighting**: Each of the calculated values (temperature, wind speed, and rainfall) is normalized across the day. Then, a weighted sum of these normalized values is calculated based on your selected importance for each weather parameter.

4. **Final Score**: The total score is normalized to a 0-1 range, providing a final weather score that helps you understand the overall weather condition for the selected date.