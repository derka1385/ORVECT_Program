class VehicleResolutionError(Exception): pass
class VinValidationError(VehicleResolutionError): pass
class ProviderUnavailableError(VehicleResolutionError): pass
class ProviderResponseError(VehicleResolutionError): pass
