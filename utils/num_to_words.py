from num2words import num2words

def convert_integer(val):
    """Converts an integer to Indian English words, removing commas, hyphens, and 'and'."""
    if val == 0:
        return "Zero"
        
    raw = num2words(val, lang='en_IN')
    
    # Replace commas and hyphens with spaces
    raw = raw.replace(',', ' ').replace('-', ' ')
    
    # Split into words and exclude 'and'
    words = raw.split()
    cleaned_words = [w for w in words if w.lower() != 'and']
    
    # Reassemble and convert to title case
    return ' '.join(cleaned_words).title()

def amount_to_words_indian(amount):
    """
    Converts a float or int amount to Indian English text representation.
    Examples:
      1000 -> One Thousand
      25750 -> Twenty Five Thousand Seven Hundred Fifty
      150000 -> One Lakh Fifty Thousand
    """
    try:
        # Convert float to int if there's no fractional part
        if isinstance(amount, float):
            if amount.is_integer():
                amount = int(amount)
            else:
                # If there's a decimal, format as Rupees and Paise
                parts = f"{amount:.2f}".split('.')
                rupees = int(parts[0])
                paise = int(parts[1])
                
                rupees_words = convert_integer(rupees)
                if paise > 0:
                    paise_words = convert_integer(paise)
                    return f"{rupees_words} Rupees and {paise_words} Paise"
                else:
                    return rupees_words
                    
        return convert_integer(int(amount))
    except Exception as e:
        # Graceful fallback to string conversion in case of library failure
        return str(amount)
