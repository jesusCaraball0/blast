from django import forms
from django.core.validators import FileExtensionValidator

class ClassifyForm(forms.Form):
    file = forms.FileField(
        label="Upload Spectrum",
        validators=[FileExtensionValidator(allowed_extensions=['txt', 'dat', 'ascii', 'csv'])],
        help_text="Upload a spectrum file (text format, two columns: wavelength and flux)"
    )
    
    # Analysis Options
    MODEL_CHOICES = [
        ('dash', 'Dash Model'),
        ('transformer', 'Transformer Model'),
    ]
    model = forms.ChoiceField(
        choices=MODEL_CHOICES, 
        initial='dash',
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    smoothing = forms.IntegerField(
        initial=0,
        min_value=0,
        max_value=20,
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )
    
    min_wave = forms.IntegerField(
        label="Min Wavelength",
        initial=3500,
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )
    
    max_wave = forms.IntegerField(
        label="Max Wavelength",
        initial=10000,
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )
    
    known_z = forms.BooleanField(
        label="Known Redshift",
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    
    redshift = forms.FloatField(
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.001'})
    )

    def clean(self):
        cleaned_data = super().clean()
        known_z = cleaned_data.get('known_z')
        redshift = cleaned_data.get('redshift')
        model = cleaned_data.get('model')

        if known_z and redshift is None:
            self.add_error('redshift', "Redshift is required when 'Known Redshift' is checked.")
        
        if model == 'transformer' and redshift is None:
             self.add_error('redshift', "Redshift is required for Transformer model.")

        return cleaned_data

class BatchForm(forms.Form):
    zip_file = forms.FileField(
        label="Upload Zip File",
        validators=[FileExtensionValidator(allowed_extensions=['zip'])],
        help_text="Upload a ZIP file containing spectrum files."
    )
    model = forms.ChoiceField(
        choices=ClassifyForm.MODEL_CHOICES, 
        initial='dash',
        widget=forms.Select(attrs={'class': 'form-control'})
    )
