import re
from ..domain.enums import CheckDigitStatus
from ..domain.models import VinValidationResult
VALUES={**{str(i):i for i in range(10)},**dict(zip("ABCDEFGHJKLMNPRSTUVWXYZ",[1,2,3,4,5,6,7,8,1,2,3,4,5,7,9,2,3,4,5,6,7,8,9]))}
WEIGHTS=[8,7,6,5,4,3,2,10,0,9,8,7,6,5,4,3,2]
class VinValidator:
    def validate(self,raw:str)->VinValidationResult:
        vin=re.sub(r"[\s-]","",raw or "").upper(); errors=[]; warnings=[]
        if not vin: errors.append("Le VIN est obligatoire.")
        if re.search(r"[^A-HJ-NPR-Z0-9*]",vin): errors.append("Le VIN contient un caractère invalide ou I, O, Q.")
        complete=len(vin)==17 and "*" not in vin
        if len(vin)>17: errors.append("Le VIN ne peut pas dépasser 17 caractères.")
        if len(vin)<3: errors.append("Un VIN partiel doit contenir au moins 3 caractères.")
        if not complete and not errors: warnings.append("VIN partiel : le décodage et la précision seront limités.")
        status=CheckDigitStatus.unknown
        if complete:
            if vin[0] in "12345":
                total=sum(VALUES.get(ch,0)*weight for ch,weight in zip(vin,WEIGHTS)); expected="X" if total%11==10 else str(total%11); status=CheckDigitStatus.valid if vin[8]==expected else CheckDigitStatus.invalid
                if status==CheckDigitStatus.invalid: warnings.append("Le caractère de contrôle nord-américain ne correspond pas.")
            else: status=CheckDigitStatus.not_applicable
        return VinValidationResult(normalized_vin=vin,is_valid_format=not errors,is_complete=complete,check_digit_status=status,warnings=warnings,errors=errors)
