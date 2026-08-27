import json
import os
import folium
import pydeck as pdk

INPUT_JSON = "output/ridge_elevation_routes.json"
OUTPUT_HTML = "output/ridge_routes_map.html"

def main():
    if not os.path.exists(INPUT_JSON):
        print(f"Error: {INPUT_JSON} not found.")
        return

    with open(INPUT_JSON, "r") as f:
        data = json.load(f)

    top_routes = data.get("master_top100", [])
    if not top_routes:
        print("No routes found.")
        return

    # Deck.GL visualization
    path_data = []
    
    # We will color code them by their average elevation score
    # Find max score to normalize
    max_score = max(r["avg_elevation_score"] for r in top_routes) if top_routes else 1
    
    for route in top_routes:
        path = []
        for c in route["cell_coordinates"]:
            path.append([c["lng"], c["lat"]])
            
        score = route["avg_elevation_score"]
        # Color gradient: high score = Red, lower score = Yellow
        intensity = min(255, int((score / max_score) * 255))
        color = [255, 255 - intensity, 0, 200]
        
        path_data.append({
            "path": path,
            "score": score,
            "color": color,
            "width": 15,
            "distance_km": route["avg_distance_km"]
        })

    view_state = pdk.ViewState(
        latitude=41.1496,
        longitude=-8.6109,
        zoom=13,
        pitch=45,
        bearing=0
    )

    path_layer = pdk.Layer(
        "PathLayer",
        path_data,
        pickable=True,
        get_color="color",
        width_scale=1,
        width_min_pixels=4,
        get_path="path",
        get_width="width"
    )

    tooltip = {
        "html": "<b>Ridge Elevation Score:</b> {score} points<br/><b>Length:</b> {distance_km} km",
        "style": {"color": "white", "backgroundColor": "black"}
    }

    deck = pdk.Deck(
        layers=[path_layer],
        initial_view_state=view_state,
        map_style="mapbox://styles/mapbox/dark-v10",
        tooltip=tooltip
    )

    deck.to_html(OUTPUT_HTML)
    print(f"✓ Saved 3D Ridge Routes Map to {OUTPUT_HTML}")

if __name__ == "__main__":
    main()
