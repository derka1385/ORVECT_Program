def mask_vin(vin:str)->str:
    return "*"*max(0,len(vin)-6)+vin[-6:]
