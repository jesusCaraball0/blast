from django.shortcuts import render
from django.contrib import messages
from django.conf import settings
from django.http import HttpResponseRedirect
from django.urls import reverse

from astrodash.forms import ClassifyForm, BatchForm
from astrodash.services import get_spectrum_processing_service, get_classification_service, get_spectrum_service
from astrodash.core.exceptions import AppException
from asgiref.sync import async_to_sync
from bokeh.embed import components
from bokeh.plotting import figure
from bokeh.models import ColumnDataSource, HoverTool

def landing_page(request):
    """
    Renders the Astrodash landing page.
    """
    return render(request, 'astrodash/index.html')

def classify(request):
    """
    Handles spectrum classification via the UI.
    """
    form = ClassifyForm(request.POST or None, request.FILES or None)
    context = {'form': form}
    
    if request.method == 'POST':
        if form.is_valid():
            uploaded_file = request.FILES['file']
            
            # Prepare params for services
            params = {
                'smoothing': form.cleaned_data['smoothing'],
                'minWave': form.cleaned_data['min_wave'],
                'maxWave': form.cleaned_data['max_wave'],
                'knownZ': form.cleaned_data['known_z'],
                'zValue': form.cleaned_data['redshift'],
                'modelType': form.cleaned_data['model'],
            }

            try:
                # Reuse the service logic
                spectrum_service = get_spectrum_service()
                processing_service = get_spectrum_processing_service()
                classification_service = get_classification_service()
                
                # 1. Read Spectrum
                spectrum = async_to_sync(spectrum_service.get_spectrum_data)(
                    file=uploaded_file, 
                    osc_ref=None
                )
                
                # 2. Process Spectrum
                processed = async_to_sync(processing_service.process_spectrum_with_params)(
                    spectrum=spectrum,
                    params=params,
                )
                
                # 3. Classify
                classification = async_to_sync(classification_service.classify_spectrum)(
                    spectrum=processed,
                    model_type=params['modelType'],
                    user_model_id=None,
                    params=params,
                )
                
                # 4. Generate Plot
                plot_script, plot_div = _create_bokeh_plot(processed)
                
                context.update({
                    'results': classification.results,
                    'plot_script': plot_script,
                    'plot_div': plot_div,
                    'model_type': classification.model_type,
                    'success': True
                })
                
            except AppException as e:
                messages.error(request, f"Processing Error: {e.message}")
            except Exception as e:
                messages.error(request, f"An unexpected error occurred: {str(e)}")
                
    return render(request, 'astrodash/classify.html', context)

def batch_process(request):
    """
    Handles batch processing UI.
    Placeholder for now.
    """
    form = BatchForm(request.POST or None, request.FILES or None)
    context = {'form': form}
    if request.method == 'POST' and form.is_valid():
        # Implementation for batch processing output
        pass 
        
    return render(request, 'astrodash/batch.html', context)

def _create_bokeh_plot(spectrum):
    """
    Creates a simple Bokeh plot for the spectrum.
    """
    source = ColumnDataSource(data=dict(x=spectrum.x, y=spectrum.y))
    
    p = figure(
        title="Spectrum", 
        x_axis_label='Wavelength (Å)', 
        y_axis_label='Flux',
        height=400,
        sizing_mode="stretch_width",
        tools="pan,box_zoom,reset,save"
    )
    
    p.line('x', 'y', source=source, line_width=2, color="#1976d2")
    
    p.add_tools(HoverTool(
        tooltips=[
            ('Wavelength', '@x{0.0}'),
            ('Flux', '@y{0.00e}'),
        ],
        mode='vline'
    ))
    
    # Styling to match dark/space theme loosely or keep it clean
    p.background_fill_color = "#f5f5f5"
    p.border_fill_color = "#ffffff"
    
    return components(p)
