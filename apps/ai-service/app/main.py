from __future__ import annotations

from math import exp
from typing import Dict

from fastapi import FastAPI
from pydantic import BaseModel, Field

app = FastAPI(title="Modality-Flow AI Service", version="1.1.0")


class PredictRequest(BaseModel):
    station_capacity: int = Field(gt=0)
    bikes_available: int = Field(ge=0)
    hour: int = Field(ge=0, le=23)
    day_of_week: int = Field(ge=0, le=6)
    temperature: float = 20
    precipitation: float = 0
    wind_speed: float = 10
    aqi: int = Field(default=3, ge=1, le=6)


class ScoreRequest(BaseModel):
    duration_minutes: float = Field(gt=0)
    co2_grams: float = Field(ge=0)
    comfort: float = Field(ge=0, le=1)
    availability: float = Field(ge=0, le=1)
    weather_penalty: float = Field(default=0, ge=0, le=1)
    pollution_penalty: float = Field(default=0, ge=0, le=1)
    traffic_index: float = Field(default=0, ge=0, le=1)


@app.get("/")
def root():
    return {"service": "Modality-Flow AI", "status": "ok", "model_version": "mobility-rf-sim-v1"}


@app.post("/predict")
def predict(req: PredictRequest):
    rush_hour = 1 if 7 <= req.hour <= 9 or 17 <= req.hour <= 19 else 0
    weekend = 1 if req.day_of_week in (5, 6) else 0
    weather_drag = min(5, req.precipitation * 1.6 + max(0, req.wind_speed - 22) * 0.08)
    temperature_drag = 2.2 if req.temperature < 4 or req.temperature > 35 else 0
    pollution_drag = 1.3 if req.aqi >= 5 else 0
    leisure_lift = 1.4 if weekend and 10 <= req.hour <= 18 and req.precipitation < 1 else 0
    commuter_delta = 2.6 * rush_hour - weather_drag - temperature_drag - pollution_drag + leisure_lift

    predicted = round(req.bikes_available - commuter_delta)
    predicted = max(0, min(req.station_capacity, predicted))
    volatility = abs(commuter_delta) / max(req.station_capacity, 1)
    confidence = max(0.61, min(0.92, 0.88 - volatility))

    return {
        "predicted_bikes_30min": predicted,
        "confidence": round(confidence, 2),
        "model_version": "mobility-rf-sim-v1",
        "features": {
            "rush_hour": rush_hour,
            "weekend": weekend,
            "weather_drag": round(weather_drag, 2),
            "pollution_drag": round(pollution_drag, 2),
        },
    }


@app.post("/score")
def score(req: ScoreRequest):
    duration_component = 100 / (1 + exp((req.duration_minutes - 22) / 8))
    co2_component = max(0, 100 - req.co2_grams * 0.22)
    comfort_component = req.comfort * 100
    availability_component = req.availability * 100
    penalty_component = (req.weather_penalty * 12) + (req.pollution_penalty * 10) + (req.traffic_index * 8)

    weighted = (
        duration_component * 0.34
        + co2_component * 0.24
        + comfort_component * 0.18
        + availability_component * 0.24
        - penalty_component
    )
    final_score = round(max(0, min(100, weighted)), 2)
    breakdown: Dict[str, float] = {
        "duration": round(duration_component, 2),
        "co2": round(co2_component, 2),
        "comfort": round(comfort_component, 2),
        "availability": round(availability_component, 2),
        "penalties": round(penalty_component, 2),
    }
    return {"score": final_score, "breakdown": breakdown, "model_version": "mobility-score-v1"}
