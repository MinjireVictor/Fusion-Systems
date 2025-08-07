# phonebridge/utils/phone_normalizer.py

import re
import logging
from typing import Optional, Dict, List

logger = logging.getLogger('phonebridge')

class PhoneNormalizer:
    """
    Phone number normalizer with Kenya focus and international extensibility
    """
    
    # Kenya-specific patterns
    KENYA_COUNTRY_CODE = '254'
    KENYA_PATTERNS = {
        # Safaricom, Airtel patterns
        'mobile': [
            r'^(\+?254|0)?([17]\d{8})$',  # 7xx, 1xx series
        ],
        # Telkom Kenya landlines
        'landline': [
            r'^(\+?254|0)?([2-6]\d{7,8})$',  # 2x, 3x, 4x, 5x, 6x series
        ]
    }
    
    # International patterns (extensible)
    INTERNATIONAL_PATTERNS = {
        'us': {
            'country_code': '1',
            'patterns': [r'^(\+?1)?([2-9]\d{9})$']
        },
        'uk': {
            'country_code': '44',
            'patterns': [r'^(\+?44|0)?([1-9]\d{8,9})$']
        },
        # Add more countries as needed
    }
    
    def __init__(self, default_country: str = 'kenya'):
        """
        Initialize normalizer with default country
        
        Args:
            default_country: Default country for normalization ('kenya', 'us', 'uk', etc.)
        """
        self.default_country = default_country.lower()
        logger.debug(f"PhoneNormalizer initialized with default country: {self.default_country}")
    
    def normalize(self, phone_number: str, country: Optional[str] = None) -> Dict[str, any]:
        """
        Normalize phone number to international format
        
        Args:
            phone_number: Raw phone number string
            country: Specific country to try (overrides default)
            
        Returns:
            Dict with:
                - normalized: Normalized number in +XXX format
                - original: Original input
                - country: Detected/used country
                - valid: Boolean indicating if normalization successful
                - type: 'mobile', 'landline', or 'unknown'
                - formats: List of alternative formats
        """
        if not phone_number:
            return self._empty_result()
        
        # Clean input
        cleaned = self._clean_phone_number(phone_number)
        if not cleaned:
            return self._invalid_result(phone_number)
        
        # Try specified country first, then default, then all
        countries_to_try = []
        if country:
            countries_to_try.append(country.lower())
        if self.default_country not in countries_to_try:
            countries_to_try.append(self.default_country)
        
        # Try Kenya first (our primary use case)
        if 'kenya' not in countries_to_try:
            countries_to_try.insert(0, 'kenya')
        
        # Attempt normalization
        for country_code in countries_to_try:
            result = self._try_normalize_for_country(cleaned, country_code)
            if result['valid']:
                return result
        
        # If all fails, try international patterns
        for country_name, config in self.INTERNATIONAL_PATTERNS.items():
            if country_name in countries_to_try:
                continue
            result = self._try_normalize_international(cleaned, country_name, config)
            if result['valid']:
                return result
        
        # Return invalid result with original
        return self._invalid_result(phone_number, cleaned)
    
    def _clean_phone_number(self, phone: str) -> str:
        """Remove all non-digit characters except +"""
        if not phone:
            return ""
        
        # Keep only digits and leading +
        cleaned = re.sub(r'[^\d+]', '', str(phone).strip())
        
        # Ensure + is only at the beginning
        if '+' in cleaned:
            parts = cleaned.split('+')
            cleaned = '+' + ''.join(parts[1:])
        
        return cleaned
    
    def _try_normalize_for_country(self, cleaned_phone: str, country: str) -> Dict[str, any]:
        """Try to normalize for specific country"""
        
        if country == 'kenya':
            return self._normalize_kenya(cleaned_phone)
        elif country in self.INTERNATIONAL_PATTERNS:
            config = self.INTERNATIONAL_PATTERNS[country]
            return self._try_normalize_international(cleaned_phone, country, config)
        else:
            return self._invalid_result(cleaned_phone)
    
    def _normalize_kenya(self, phone: str) -> Dict[str, any]:
        """Normalize Kenya phone numbers"""
        
        # Try mobile patterns
        for pattern in self.KENYA_PATTERNS['mobile']:
            match = re.match(pattern, phone)
            if match:
                prefix, number = match.groups()
                normalized = f"+{self.KENYA_COUNTRY_CODE}{number}"
                return {
                    'normalized': normalized,
                    'original': phone,
                    'country': 'kenya',
                    'valid': True,
                    'type': 'mobile',
                    'formats': self._generate_kenya_formats(number)
                }
        
        # Try landline patterns
        for pattern in self.KENYA_PATTERNS['landline']:
            match = re.match(pattern, phone)
            if match:
                prefix, number = match.groups()
                normalized = f"+{self.KENYA_COUNTRY_CODE}{number}"
                return {
                    'normalized': normalized,
                    'original': phone,
                    'country': 'kenya',
                    'valid': True,
                    'type': 'landline',
                    'formats': self._generate_kenya_formats(number)
                }
        
        return self._invalid_result(phone)
    
    def _try_normalize_international(self, phone: str, country: str, config: Dict) -> Dict[str, any]:
        """Try to normalize using international patterns"""
        
        country_code = config['country_code']
        patterns = config['patterns']
        
        for pattern in patterns:
            match = re.match(pattern, phone)
            if match:
                prefix, number = match.groups()
                normalized = f"+{country_code}{number}"
                return {
                    'normalized': normalized,
                    'original': phone,
                    'country': country,
                    'valid': True,
                    'type': 'unknown',  # Could be enhanced per country
                    'formats': [normalized, number]
                }
        
        return self._invalid_result(phone)
    
    def _generate_kenya_formats(self, number: str) -> List[str]:
        """Generate common Kenya phone number formats"""
        normalized = f"+{self.KENYA_COUNTRY_CODE}{number}"
        return [
            normalized,                           # +254712345678
            f"{self.KENYA_COUNTRY_CODE}{number}", # 254712345678
            f"0{number}",                         # 0712345678
            number                                # 712345678
        ]
    
    def _empty_result(self) -> Dict[str, any]:
        """Return result for empty input"""
        return {
            'normalized': '',
            'original': '',
            'country': '',
            'valid': False,
            'type': 'unknown',
            'formats': []
        }
    
    def _invalid_result(self, original: str, cleaned: str = None) -> Dict[str, any]:
        """Return result for invalid phone number"""
        return {
            'normalized': cleaned or original,
            'original': original,
            'country': 'unknown',
            'valid': False,
            'type': 'unknown',
            'formats': [original]
        }
    
    def batch_normalize(self, phone_numbers: List[str], country: Optional[str] = None) -> List[Dict[str, any]]:
        """
        Normalize multiple phone numbers
        
        Args:
            phone_numbers: List of phone number strings
            country: Country to use for all numbers
            
        Returns:
            List of normalization results
        """
        results = []
        for phone in phone_numbers:
            result = self.normalize(phone, country)
            results.append(result)
        
        return results
    
    def is_valid_kenya_mobile(self, phone: str) -> bool:
        """Quick check if phone number is valid Kenya mobile"""
        result = self.normalize(phone, 'kenya')
        return result['valid'] and result['type'] == 'mobile'
    
    def get_search_variants(self, phone: str) -> List[str]:
        """
        Get all possible formats for searching in CRM
        
        Args:
            phone: Phone number to get variants for
            
        Returns:
            List of phone number variants for searching
        """
        result = self.normalize(phone)
        if not result['valid']:
            # Even invalid numbers might match something in CRM
            cleaned = self._clean_phone_number(phone)
            return [phone, cleaned] if cleaned != phone else [phone]
        
        return result['formats']


# Convenience function for simple usage
def normalize_phone(phone_number: str, country: str = 'kenya') -> str:
    """
    Simple function to get normalized phone number
    
    Args:
        phone_number: Phone number to normalize
        country: Country for normalization
        
    Returns:
        Normalized phone number or original if invalid
    """
    normalizer = PhoneNormalizer(country)
    result = normalizer.normalize(phone_number)
    return result['normalized'] if result['valid'] else phone_number


# Example usage and testing
if __name__ == "__main__":
    # Test Kenya numbers
    normalizer = PhoneNormalizer('kenya')
    
    test_numbers = [
        "0712345678",      # Kenya mobile
        "+254712345678",   # Kenya mobile international
        "254712345678",    # Kenya mobile without +
        "712345678",       # Kenya mobile without prefix
        "020-1234567",     # Kenya landline
        "+254-20-1234567", # Kenya landline international
        "1234567890",      # Invalid
        "+1-555-123-4567", # US number
    ]
    
    print("Phone Number Normalization Tests:")
    print("=" * 50)
    
    for phone in test_numbers:
        result = normalizer.normalize(phone)
        print(f"Input: {phone}")
        print(f"  Normalized: {result['normalized']}")
        print(f"  Valid: {result['valid']}")
        print(f"  Country: {result['country']}")
        print(f"  Type: {result['type']}")
        print(f"  Formats: {result['formats']}")
        print()