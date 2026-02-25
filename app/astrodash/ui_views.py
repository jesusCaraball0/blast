from django.shortcuts import render
from django.contrib import messages
from django.conf import settings
from django.http import HttpResponseRedirect, FileResponse, Http404
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.urls import reverse
from pathlib import Path

from astrodash.forms import ClassifyForm, BatchForm, ModelSelectionForm
from astrodash.services import get_spectrum_processing_service, get_classification_service, get_spectrum_service, get_model_service
from astrodash.core.exceptions import AppException
from asgiref.sync import async_to_sync
from bokeh.embed import components
from bokeh.plotting import figure
from bokeh.models import ColumnDataSource, HoverTool
import json

def landing_page(request):
    """
    Renders the Astrodash landing page.
    """
    return render(request, 'astrodash/index.html')


@xframe_options_sameorigin
def dash_twins(request):
    """
    Serves the DASH Twins Explorer static HTML (embedding visualization).
    File lives under the astrodash app: astrodash/explorer/dash_twinsfromspace.html
    """
    path = Path(settings.BASE_DIR) / "astrodash" / "explorer" / "dash_twinsfromspace.html"
    if not path.is_file():
        raise Http404("DASH Twins Explorer file not found.")
    return FileResponse(
        open(path, "rb"),
        content_type="text/html",
        as_attachment=False,
    )


def model_selection(request):
    """
    Handles model selection page - allows choosing between dash/transformer or uploading a custom model.
    """
    # Clear messages carried over from other pages (e.g. classify/batch processing errors)
    # so the model selection page doesn't show unrelated errors.
    list(messages.get_messages(request))

    action_type = request.GET.get('action', 'classify')  # 'classify' or 'batch'
    form = ModelSelectionForm(request.POST or None, request.FILES or None)
    
    if request.method == 'POST':
        form = ModelSelectionForm(request.POST, request.FILES)
        if form.is_valid():
            model_type = form.cleaned_data.get('model_type')
            action_type = form.cleaned_data.get('action_type') or action_type
            
            # Handle model upload
            if model_type == 'upload':
                model_file = request.FILES.get('model_file')
                class_mapping = form.cleaned_data.get('class_mapping')
                input_shape = form.cleaned_data.get('input_shape')
                model_name = form.cleaned_data.get('model_name')
                model_description = form.cleaned_data.get('model_description')
                
                try:
                    model_service = get_model_service()
                    user_model, model_info = async_to_sync(model_service.upload_model)(
                        model_content=model_file.read(),
                        filename=model_file.name,
                        class_mapping_str=class_mapping,
                        input_shape_str=input_shape,
                        name=model_name,
                        description=model_description,
                        owner=request.user.username if request.user.is_authenticated else None,
                    )
                    
                    # Store model ID in session for use in classify/batch views
                    request.session['selected_model_id'] = user_model.id
                    request.session['selected_model_type'] = 'user_uploaded'
                    messages.success(request, f"Model '{model_name}' uploaded successfully!")
                    
                except AppException as e:
                    messages.error(request, f"Model upload error: {e.message}")
                    return render(request, 'astrodash/model_selection.html', {'form': form, 'action_type': action_type})
                except Exception as e:
                    messages.error(request, f"An unexpected error occurred during model upload: {str(e)}")
                    return render(request, 'astrodash/model_selection.html', {'form': form, 'action_type': action_type})
            else:
                # Store selected model type in session
                request.session['selected_model_type'] = model_type
                request.session.pop('selected_model_id', None)  # Clear any previous user model
            
            # Redirect to the appropriate page
            if action_type == 'batch':
                return HttpResponseRedirect(reverse('astrodash:batch_process_ui'))
            else:
                return HttpResponseRedirect(reverse('astrodash:classify'))
    
    # Pre-populate action_type in form
    form.fields['action_type'].initial = action_type
    return render(request, 'astrodash/model_selection.html', {'form': form, 'action_type': action_type})

def classify(request):
    """
    Handles spectrum classification via the UI.
    """
    # Get model selection from session (set by model_selection view)
    selected_model_type = request.session.get('selected_model_type')
    selected_model_id = request.session.get('selected_model_id', None)
    
    # If no model selected, redirect to model selection
    if selected_model_type is None:
        return HttpResponseRedirect(reverse('astrodash:model_selection') + '?action=classify')
    
    form = ClassifyForm(request.POST or None, request.FILES or None)
    # Set the model from session
    form.fields['model'].initial = selected_model_type if selected_model_type != 'user_uploaded' else 'transformer'
    context = {
        'form': form,
    }
    
    if request.method == 'POST':
        if form.is_valid():
            uploaded_file = request.FILES.get('file')
            supernova_name = form.cleaned_data.get('supernova_name')

            # Use model from session, not form (form model field is hidden/disabled)
            model_type = selected_model_type
            if model_type == 'user_uploaded':
                model_type = 'user_uploaded'
            
            # Prepare params for services
            params = {
                'smoothing': form.cleaned_data['smoothing'],
                'minWave': form.cleaned_data['min_wave'],
                'maxWave': form.cleaned_data['max_wave'],
                'knownZ': form.cleaned_data['known_z'],
                'zValue': form.cleaned_data['redshift'],
                'modelType': model_type if model_type != 'user_uploaded' else 'transformer',  # Fallback for display
            }

            try:
                # Reuse the service logic
                spectrum_service = get_spectrum_service()
                processing_service = get_spectrum_processing_service()
                classification_service = get_classification_service()
                
                # 1. Read Spectrum
                # If file is provided, use it. Otherwise use supernova_name (osc_ref)
                spectrum = async_to_sync(spectrum_service.get_spectrum_data)(
                    file=uploaded_file, 
                    osc_ref=supernova_name
                )
                
                # 2. Process Spectrum
                processed = async_to_sync(processing_service.process_spectrum_with_params)(
                    spectrum=spectrum,
                    params=params,
                )
                
                # 3. Classify
                classification = async_to_sync(classification_service.classify_spectrum)(
                    spectrum=processed,
                    model_type=model_type,
                    user_model_id=selected_model_id,
                    params=params,
                )
                
                # 4. Generate Plot
                plot_script, plot_div = _create_bokeh_plot(processed)
                
                # Workaround for template filter issue: Format in view
                formatted_results = _format_results(classification.results)

                context.update({
                    'results': formatted_results,
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


from astrodash.services import get_batch_processing_service

def batch_process(request):
    """
    Handles batch processing UI.
    Support for both ZIP file uploads and multiple individual file uploads.
    """
    # Get model selection from session (set by model_selection view)
    selected_model_type = request.session.get('selected_model_type')
    selected_model_id = request.session.get('selected_model_id', None)
    
    # If no model selected, redirect to model selection
    if selected_model_type is None:
        return HttpResponseRedirect(reverse('astrodash:model_selection') + '?action=batch')
    
    form = BatchForm(request.POST or None, request.FILES or None)
    # Set the model from session
    form.fields['model'].initial = selected_model_type if selected_model_type != 'user_uploaded' else 'dash'
    context = {'form': form}

    if request.method == 'POST':
        # Manually attach files to form for validation if needed, though form.is_valid handles request.FILES
        # For the 'files' field which uses ClearableFileInput key 'files', we need to check request.FILES.getlist
        files = request.FILES.getlist('files')
        
        if form.is_valid():
            try:
                # Use model from session, not form
                model_type = selected_model_type
                if model_type == 'user_uploaded':
                    model_type = 'user_uploaded'
                
                # Prepare params
                params = {
                    'smoothing': form.cleaned_data['smoothing'],
                    'minWave': form.cleaned_data['min_wave'],
                    'maxWave': form.cleaned_data['max_wave'],
                    'knownZ': form.cleaned_data['known_z'],
                    'zValue': form.cleaned_data['redshift'],
                    'calculateRlap': form.cleaned_data['calculate_rlap'],
                    'modelType': model_type if model_type != 'user_uploaded' else 'dash',  # Fallback for display
                }
                
                batch_service = get_batch_processing_service()
                
                zip_file = form.cleaned_data.get('zip_file')
                
                results = {}
                
                files_to_process = None
                if zip_file:
                    files_to_process = zip_file
                elif files:
                    files_to_process = files
                else:
                    messages.error(request, "Please upload a ZIP file or select multiple files.")
                    return render(request, 'astrodash/batch.html', context)
                
                results = async_to_sync(batch_service.process_batch)(
                    files=files_to_process,
                    params=params,
                    model_type=model_type,
                    model_id=selected_model_id
                )

                # Format results for template
                formatted_results = _format_batch_results(results, params)
                context['results'] = formatted_results
                context['success'] = True

            except AppException as e:
                messages.error(request, f"Batch Processing Error: {e.message}")
            except Exception as e:
                 messages.error(request, f"An unexpected error occurred during batch processing: {str(e)}")

    return render(request, 'astrodash/batch.html', context)

def _format_batch_results(results, params):
    """
    Format batch results for display in the template.
    """
    formatted = {}
    for filename, result in results.items():
        formatted_item = {}
        
        # Check for error
        if result.get('error'):
            formatted_item['error'] = result['error']
        else:
            # Extract classification data
            classification = result.get('classification', {})
            best_match = classification.get('best_match', {})
            
            formatted_item['type'] = best_match.get('type', '-')
            formatted_item['age'] = best_match.get('age', '-')
            
            prob = best_match.get('probability')
            formatted_item['probability'] = f"{prob:.4f}" if prob is not None else '-'
            
            formatted_item['redshift'] = best_match.get('redshift', '-')
            
            # RLAP only for Dash model and if requested
            if params.get('modelType') == 'dash' and params.get('calculateRlap'):
                formatted_item['rlap'] = best_match.get('rlap', '-')
            else:
                 formatted_item['rlap'] = '-'
                 
        formatted[filename] = formatted_item
        
    return formatted

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

def _format_results(results):
    """
    Format results for display in the template to avoid filter issues.
    """
    formatted_matches = []
    
    # helper to get attributes from dict or object
    def get_attr(obj, attr, default=None):
        if isinstance(obj, dict):
            return obj.get(attr, default)
        return getattr(obj, attr, default)

    # Check if results has best_matches
    best_matches = get_attr(results, 'best_matches', [])
    
    for match in best_matches:
        # Create a dict representation
        match_dict = {}
        
        # Extract fields needed for template
        for field in ['type', 'age', 'probability', 'redshift', 'reliable']:
            match_dict[field] = get_attr(match, field)
            
        # Add formatted probability
        if match_dict['probability'] is not None:
             match_dict['formatted_probability'] = f"{match_dict['probability']:.4f}"
        else:
             match_dict['formatted_probability'] = ""

        formatted_matches.append(match_dict)
        
    return {'best_matches': formatted_matches}
