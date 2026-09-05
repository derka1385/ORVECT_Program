from app.core.config import settings

CRITICAL=("make","model","generation","engine_name","engine_code","engine_power_hp","fuel_type","transmission_type","model_year")
class VehicleConfidence:
    def calculate(self,vehicle:dict,provider_count:int,contradictions:list[str],user_confirmed=False)->tuple[float,list[str],str]:
        present=sum(bool(vehicle.get(field)) for field in CRITICAL);score=.25+.065*present
        if vehicle.get("engine_code"):score+=.10
        if vehicle.get("tecdoc_k_type"):score+=.08
        if provider_count>1:score+=.08
        score-=.18*len(contradictions)
        if user_confirmed:score=max(score,.95)
        score=round(max(0,min(1,score)),2);missing=[field for field in CRITICAL if not vehicle.get(field)]
        status="resolved" if score>=settings.vehicle_confidence_reliable and not contradictions else "confirmation_required" if score>=settings.vehicle_confidence_ambiguous else "vin_required"
        return score,missing,status
