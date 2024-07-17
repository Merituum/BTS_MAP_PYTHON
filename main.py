import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QLineEdit, QPushButton, QProgressBar
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtCore import QThread, pyqtSignal
import folium
import pandas as pd
import io
import requests
from geopy.distance import geodesic

OPENCAGE_API_KEY = '329efb3e6b1d4291b7559e2409deb4d4'
RADIUS_KM = 10  # Radius to filter transmitters

class Worker(QThread):
    progress = pyqtSignal(int)
    result = pyqtSignal(pd.DataFrame)
    
    def __init__(self, location):
        super().__init__()
        self.location = location

    def run(self):
        try:
            df = pd.read_csv('output.csv', delimiter=';', usecols=['siec_id', 'LONGuke', 'LATIuke', 'StationId'])
            # Filter data to include only transmitters within a certain radius
            filtered_df = self.filter_transmitters_by_location(df, self.location, RADIUS_KM)
            self.result.emit(filtered_df)
        except Exception as e:
            print(f"Error reading CSV file: {e}")
            self.result.emit(pd.DataFrame())  # Emit empty dataframe in case of error

    def filter_transmitters_by_location(self, df, location, radius_km):
        total = len(df)
        filtered_rows = []
        for i, row in df.iterrows():
            if geodesic(location, (row['LATIuke'], row['LONGuke'])).km <= radius_km:
                filtered_rows.append(row)
            self.progress.emit(int((i / total) * 100))
        return pd.DataFrame(filtered_rows)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LTE/5G Network Analyzer")
        self.setGeometry(100, 100, 800, 600)
        
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        
        self.layout = QVBoxLayout(self.central_widget)
        
        self.address_input = QLineEdit(self)
        self.address_input.setPlaceholderText("Enter address")
        self.layout.addWidget(self.address_input)
        
        self.show_map_button = QPushButton("Show Map", self)
        self.show_map_button.clicked.connect(self.show_map)
        self.layout.addWidget(self.show_map_button)
        
        self.map_view = QWebEngineView(self)
        self.layout.addWidget(self.map_view)

        self.progress_bar = QProgressBar(self)
        self.layout.addWidget(self.progress_bar)

    def show_map(self):
        address = self.address_input.text()
        if address:
            location = self.get_location_from_address(address)
            if location:
                self.start_worker(location)
            else:
                print("Could not retrieve location.")
        else:
            print("No address entered.")

    def get_location_from_address(self, address):
        # Use OpenCageData API to convert address to latitude and longitude
        url = f'https://api.opencagedata.com/geocode/v1/json?q={address}&key={OPENCAGE_API_KEY}'
        response = requests.get(url).json()
        if response and response['results']:
            lat = response['results'][0]['geometry']['lat']
            lon = response['results'][0]['geometry']['lng']
            return float(lat), float(lon)
        return None

    def start_worker(self, location):
        self.worker = Worker(location)
        self.worker.progress.connect(self.update_progress)
        self.worker.result.connect(self.display_map)
        self.worker.start()

    def update_progress(self, value):
        self.progress_bar.setValue(value)

    def display_map(self, filtered_df):
        self.progress_bar.setValue(100)  # Ensure the progress bar is full

        if filtered_df.empty:
            print("No data to display.")
            return

        lat, lon = filtered_df.iloc[0]['LATIuke'], filtered_df.iloc[0]['LONGuke']
        map_ = folium.Map(location=[lat, lon], zoom_start=15)
        folium.Marker([lat, lon], tooltip='Location').add_to(map_)

        operator_colors = {
            'T-Mobile' : 'pink',
            'Orange' : 'orange',
            'Play' : 'violet',
        }

        # Keep track of coordinates to add offset for duplicates
        coord_count = {}

        # Add markers for each transmitter in the specified town
        for index, row in filtered_df.iterrows():
            operator = row['siec_id']
            if operator == 'Plus':
                continue  # Ignore Plus operator

            trans_lat = row['LATIuke']
            trans_lon = row['LONGuke']
            station_id = row['StationId']
            transmitter_location = (trans_lat, trans_lon)

            if transmitter_location in coord_count:
                coord_count[transmitter_location] += 1
                trans_lat += coord_count[transmitter_location] * 0.0001  # Apply a small offset
                trans_lon += coord_count[transmitter_location] * 0.0001
            else:
                coord_count[transmitter_location] = 0

            # Create HTML content for tooltip
            tooltip_html = f"<b>Operator:</b> {operator}<br><b>Station ID:</b> {station_id}"
            # Add marker to the map
            print(trans_lat, trans_lon)
            color = operator_colors.get(operator)
            folium.Marker([trans_lat, trans_lon], tooltip=tooltip_html, icon=folium.Icon(color=color)).add_to(map_)

        # Save map with transmitters and display in QWebEngineView
        data = io.BytesIO()
        map_.save(data, close_file=False)
        self.map_view.setHtml(data.getvalue().decode())
        self.progress_bar.setValue(0)  # Reset the progress bar for the next use

if __name__ == "__main__":
    app = QApplication(sys.argv)
    main_window = MainWindow()
    main_window.show()
    sys.exit(app.exec_())
