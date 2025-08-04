import streamlit as st
import google.generativeai as genai
from dotenv import load_dotenv
import os
import re
from gtts import gTTS
import base64
import tempfile
from PIL import Image
import googlemaps
import re
from firecrawl import FirecrawlApp  # New import for Firecrawl

# Load environment variables
load_dotenv()

# Configure Gemini API
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-1.5-flash')

# Configure Firecrawl
firecrawl_api_key = os.getenv("FIRECRAWL_API_KEY")
firecrawl_app = FirecrawlApp(api_key=firecrawl_api_key) if firecrawl_api_key else None

def analyze_image(uploaded_file):
    """Analyze uploaded image for medical symptoms"""
    try:
        image = Image.open(uploaded_file)
        response = model.generate_content(["Analyze this medical image for symptoms, possible conditions, and urgency level. Focus on visible symptoms like rashes, wounds, swelling, or discoloration. Provide recommendations similar to the text analysis format.", image])
        return response.text
    except Exception as e:
        return f"Error analyzing image: {str(e)}"

def generate_response(user_input, language, image_analysis=None):
    """Generate health assessment using Gemini with image analysis"""
    language_instruction = {
        "English": "Provide all recommendations in English.",
        "Hindi": "Provide all recommendations in Hindi (हिंदी में).",
        "Telugu": "Provide all recommendations in Telugu (తెలుగులో)."
    }.get(language, "Provide all recommendations in English.")
    
    patient_info = f"""
Patient Information:
- Symptoms: {user_input.get('symptoms', 'Not specified')}
- Duration: {user_input.get('duration', 'Not specified')}
- Severity: {user_input.get('severity', 'Not specified')}
- Location: {user_input.get('location', 'Not specified')}
- Onset: {user_input.get('onset', 'Not specified')}
- Age: {user_input.get('age', 'Not specified')}
- Gender: {user_input.get('gender', 'Not specified')}
- Medical History: {user_input.get('medical_history', 'Not specified')}
- Current Medications: {user_input.get('medications', 'Not specified')}
- Allergies: {user_input.get('allergies', 'Not specified')}
- Lifestyle: {user_input.get('lifestyle', 'Not specified')}
"""
    
    visual_analysis = f"\n\nAdditional Visual Symptom Analysis:\n{image_analysis}" if image_analysis else ""
    
    prompt = f"""You are an AI Health Assistant. Analyze the following patient information and provide detailed recommendations:

1. Possible conditions (list 3-5 most likely, ordered by probability)
2. Urgency level (emergency, seek care soon, self-care)
3. Recommended next steps (when to see a doctor, self-care tips)
4. Any red flag symptoms to watch for
5. SPECIFIC MEDICATION RECOMMENDATIONS (both prescription and OTC options)

MEDICATION GUIDELINES:
- For common/minor issues: Suggest specific OTC medications with standard dosages
- For serious conditions: State that prescription medications are needed and list common options doctors might prescribe
- Always consider the patient's current medications and allergies
- Include both generic and brand names when available
- Provide standard adult dosages (unless pediatric case)
- Highlight important warnings (allergies, interactions, side effects)
- Still recommend doctor consultation for proper diagnosis

IMPORTANT FORMATTING:
- Urgency level must use exactly:
  * "Urgency Level: Emergency" (red)
  * "Urgency Level: Seek care soon" (orange)
  * "Urgency Level: Self-care" (green)

- Medication section must begin with: "### Medication Recommendations:"

{language_instruction}

{patient_info}
{visual_analysis}

Provide clear, actionable recommendations while emphasizing safety.
"""
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Error generating response: {str(e)}"
    
def color_urgency_level(text):
    """Add color to the urgency level in the response text"""
    if "Urgency Level: Emergency" in text:
        return re.sub(
            r"Urgency Level: Emergency", 
            r'<span style="color:red; font-weight:bold">Urgency Level: Emergency</span>', 
            text
        )
    elif "Urgency Level: Seek care soon" in text:
        return re.sub(
            r"Urgency Level: Seek care soon", 
            r'<span style="color:orange; font-weight:bold">Urgency Level: Seek care soon</span>', 
            text
        )
    elif "Urgency Level: Self-care" in text:
        return re.sub(
            r"Urgency Level: Self-care", 
            r'<span style="color:green; font-weight:bold">Urgency Level: Self-care</span>', 
            text
        )
    return text

def enhance_medication_display(text):
    """Improve the display of medication information"""
    # Highlight section header
    text = re.sub(r"### Medication Recommendations:", 
                 r'<h4 style="color:#2b5876; margin-top:20px">💊 Medication Recommendations:</h4>', 
                 text)
    
    # Highlight medication names
    text = re.sub(r"(?i)(\b(?:paracetamol|acetaminophen|ibuprofen|aspirin|omeprazole|loratadine|diphenhydramine|ranitidine|pepto-bismol)\b)", 
                 r'<span style="background-color:#979291; padding:2px 5px; border-radius:4px; border:1px solid #cce0ff">\1</span>', 
                 text)
    
    # Highlight dosage information
    text = re.sub(r"(\d+\s?mg|\d+\s?times per day|\d+\s?hours)", 
                 r'<span style="font-weight:bold; color:#0066cc">\1</span>', 
                 text)
    
    return text

def get_nearby_medical_facilities(gmaps_client, location, radius=5000):
    """Get nearby hospitals and clinics using Google Maps API"""
    try:
        if not location or gmaps_client is None:
            return None
                
        geocode_result = gmaps_client.geocode(location)
        if not geocode_result:
            return None
            
        location_coords = geocode_result[0]['geometry']['location']
        
        places_result = gmaps_client.places_nearby(
            location=location_coords,
            radius=radius,
            type='hospital|clinic|doctor',
            keyword='emergency'
        )
        
        return {
            'coordinates': location_coords,
            'places': places_result.get('results', [])
        }
    except Exception as e:
        st.error(f"Error fetching medical facilities: {str(e)}")
        return None

def show_medical_facilities_map(medical_data):
    """Display nearby medical facilities on a map"""
    if not medical_data or not medical_data.get('places'):
        st.warning("No nearby medical facilities found")
        return
    
    coordinates = medical_data['coordinates']
    places = medical_data['places']
    
    import folium
    from streamlit_folium import folium_static
    
    m = folium.Map(location=[coordinates['lat'], coordinates['lng']], zoom_start=13)
    
    for place in places[:10]:
        folium.Marker(
            location=[place['geometry']['location']['lat'], 
            place['geometry']['location']['lng']],
            popup=f"<b>{place.get('name', 'Medical Facility')}</b><br>"
                 f"Rating: {place.get('rating', 'N/A')}<br>"
                 f"Status: {place.get('business_status', 'Unknown')}",
            icon=folium.Icon(color='red', icon='plus-sign')
        ).add_to(m)
    
    folium_static(m)
    
    st.subheader("🚑 Nearby Medical Facilities")
    for i, place in enumerate(places[:5], 1):
        st.markdown(f"""
        **{i}. {place['name']}**  
        ⭐ Rating: {place.get('rating', 'Not rated')}  
        📍 Address: {place.get('vicinity', 'Address not available')}  
        """)

def text_to_speech(text, language):
    """Convert text to speech and return audio file path"""
    try:
        temp_dir = tempfile.mkdtemp()
        audio_path = os.path.join(temp_dir, "output.mp3")
        
        tld_map = {
            "English": "com",
            "Hindi": "co.in",
            "Telugu": "co.in"
        }
        lang_code = 'en' if language == "English" else 'hi'
        
        tts = gTTS(text=text, lang=lang_code, tld=tld_map.get(language, "com"), slow=False)
        tts.save(audio_path)
        return audio_path
    except Exception as e:
        st.error(f"Error in text-to-speech: {str(e)}")
        return None

def autoplay_audio(file_path):
    """Autoplay audio in the browser"""
    try:
        with open(file_path, "rb") as f:
            data = f.read()
            b64 = base64.b64encode(data).decode()
            md = f"""
                <audio controls autoplay="true">
                <source src="data:audio/mp3;base64,{b64}" type="audio/mp3">
                </audio>
                """
            st.markdown(md, unsafe_allow_html=True)
    except Exception as e:
        st.error(f"Error playing audio: {str(e)}")
    finally:
        try:
            if file_path and os.path.exists(file_path):
                os.unlink(file_path)
                os.rmdir(os.path.dirname(file_path))
        except Exception as e:
            pass

def generate_nutrition_recommendations(health_data, user_info):
    """Generate personalized nutrition advice"""
    prompt = f"""As a nutritionist, provide detailed dietary recommendations based on:
    
    Health Assessment: {health_data}
    
    Patient Information:
    - Age: {user_info['age']}
    - Gender: {user_info['gender']}
    - Conditions: {user_info['medical_history']}
    - Medications: {user_info['medications']}
    - Allergies: {user_info['allergies']}
    - Lifestyle: {user_info['lifestyle']}
    
    Provide:
    1. Recommended foods and avoidances
    2. Sample meal plan
    3. Key nutrients to focus on
    4. Hydration advice
    5. Supplement suggestions
    
    Format with clear headings and bullet points."""
    
    response = model.generate_content(prompt)
    return response.text

def extract_medication_names(text):
    """Extract medication names from the response text"""
    # Common medication patterns
    medication_pattern = r"(?i)\b(?:paracetamol|acetaminophen|ibuprofen|aspirin|omeprazole|loratadine|diphenhydramine|ranitidine|pepto-bismol|amoxicillin|doxycycline|cephalexin|azithromycin|penicillin|metformin|insulin|atorvastatin|simvastatin|lisinopril|losartan|metoprolol|propranolol|sertraline|fluoxetine|venlafaxine|tramadol|hydrocodone|oxycodone|codeine|morphine|fentanyl|diazepam|alprazolam|lorazepam|clonazepam|zolpidem|trazodone|quetiapine|risperidone|olanzapine|sumatriptan|propranolol|topiramate|valproate|carbamazepine|lamotrigine|levothyroxine|prednisone|hydrocortisone|fluticasone|salmeterol|albuterol|montelukast|levocetirizine|fexofenadine|cetirizine|pseudoephedrine|phenylephrine|dextromethorphan|guaifenesin|diphenhydramine|doxylamine|melatonin|omeprazole|lansoprazole|pantoprazole|ranitidine|famotidine|bisacodyl|senna|polyethylene glycol|loperamide|psyllium|metoclopramide|ondansetron|promethazine|dimenhydrinate|meclizine|scopolamine|warfarin|apixaban|rivaroxaban|clopidogrel|aspirin|enoxaparin|heparin|furosemide|hydrochlorothiazide|spironolactone|torsemide|finasteride|dutasteride|tamsulosin|alfuzosin|sildenafil|tadalafil|vardenafil|dapoxetine|fluconazole|clotrimazole|miconazole|terbinafine|acyclovir|valacyclovir|famciclovir|oseltamivir|zanamivir|hydroxychloroquine|ivermectin|azithromycin|doxycycline|ceftriaxone|vancomycin|meropenem|piperacillin|tazobactam|amikacin|gentamicin|tobramycin|ciprofloxacin|levofloxacin|moxifloxacin|nitrofurantoin|trimethoprim|sulfamethoxazole|metronidazole|clindamycin|linezolid|daptomycin|colistin|polymyxin b|chloramphenicol|tetracycline|minocycline|tigecycline|erythromycin|clarithromycin|azithromycin|clindamycin|vancomycin|daptomycin|linezolid|tedizolid|quinupristin|dalfopristin|telavancin|dalbavancin|oritavancin|ceftaroline|ceftobiprole|ceftolozane|tazobactam|ceftazidime|avibactam|meropenem|vaborbactam|imipenem|cilastatin|relebactam|ertapenem|doripenem|aztreonam|avibactam|plazomicin|eravacycline|omadacycline|sarecycline|lefamulin|delafloxacin|zabofloxacin|nemonoxacin|solithromycin|lefamulin|tedizolid|cadazolid|surotomycin|ridinilazole|afabicin|gepotidacin|zoliflodacin|contramid|solithromycin|lefamulin|tedizolid|cadazolid|surotomycin|ridinilazole|afabicin|gepotidacin|zoliflodacin|contramid)\b"
    
    medications = re.findall(medication_pattern, text, flags=re.IGNORECASE)
    return list(set(medications))  # Remove duplicates

def search_medication_products(medication_name):
    """Search for medication products using Firecrawl"""
    if not firecrawl_app:
        return None
    
    try:
        # Search for the medication on pharmacy websites
        search_query = f"{medication_name} site:pharmeasy.in OR site:netmeds.com OR site:1mg.com OR site:apollopharmacy.in OR site:medplusmart.com"
        
        # Use Firecrawl to search for the medication
        scraped_data = firecrawl_app.search(
            query=search_query,
            params={
                "limit": 3  # Limit to top 3 results
            }
        )
        
        # Process the results
        products = []
        for result in scraped_data.get('data', [])[:3]:  # Limit to top 3 results
            product = {
                'name': f"{medication_name.capitalize()} from {result.get('url', '').split('/')[2]}",
                'price': 'Check website for price',
                'url': result.get('url', '#'),
                'source': result.get('url', '').split('/')[2] if result.get('url') else 'Unknown'
            }
            products.append(product)
        
        return products if products else None
    except Exception as e:
        st.error(f"Error searching for medication: {str(e)}")
        return None
    

def display_medication_products(medication_name):
    """Display medication products with purchase links"""
    with st.spinner(f"Searching for {medication_name} products..."):
        products = search_medication_products(medication_name)
        
        if products:
            st.subheader(f"🛒 Purchase Options for {medication_name.capitalize()}")
            
            for i, product in enumerate(products, 1):
                st.markdown(f"""
                **{i}. {product['name']}**  
                💵 Price: {product['price']}  
                🏪 Source: {product['source']}  
                🔗 [Buy Now]({product['url']})  
                """)
        else:
            st.warning(f"Could not find purchase options for {medication_name}. Please check local pharmacies.")

def main():
    st.set_page_config(page_title="AI Health Assistant", page_icon="🩺", layout="wide")
    
    st.title("🩺 AI Health Assistant")
    st.write("Get health assessments, medication advice, emergency help, and nutrition recommendations")
    
    # Initialize Google Maps client
    gmaps = None
    try:
        if os.getenv("GOOGLE_MAPS_API_KEY"):
            gmaps = googlemaps.Client(key=os.getenv("GOOGLE_MAPS_API_KEY"))
        else:
            st.warning("Google Maps API key not found. Emergency location services will be limited.")
    except Exception as e:
        st.error(f"Failed to initialize Google Maps client: {str(e)}")
        gmaps = None

    # Check Firecrawl availability
    if not firecrawl_app:
        st.warning("Firecrawl API key not found. Medication purchase links will not be available.")

    # Language selection
    language = st.sidebar.selectbox("🌐 Select Output Language", 
                                  ["English", "Hindi", "Telugu"],
                                  index=0)
    
    # Initialize session state
    if 'response_data' not in st.session_state:
        st.session_state.response_data = {
            'text': None,
            'audio_path': None,
            'show_results': False,
            'audio_generated': False,
            'uploaded_image': None,
            'is_emergency': False,
            'show_nutrition': False,
            'nutrition_advice': None,
            'medications_found': None
        }
    
    with st.form("health_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Symptoms")
            symptoms = st.text_area("Describe your symptoms in detail", 
                                  height=100,
                                  placeholder="E.g.: 'Sharp headache behind right eye with nausea for 2 days'")
            
            uploaded_file = st.file_uploader("📸 Upload photos of visible symptoms", 
                                          type=["jpg", "jpeg", "png","webp"])
            
            if uploaded_file:
                st.session_state.response_data['uploaded_image'] = uploaded_file
                st.image(uploaded_file, caption="Uploaded Symptom Image", width=200)
            
            duration = st.text_input("⏳ Duration", 
                                   placeholder="How long have you had these symptoms?")
            
            severity = st.selectbox("🔁 Severity", 
                                  ["", "Mild", "Moderate", "Severe", "Worst pain ever"], 
                                  index=0)
            
            location = st.text_input("📍 Location", 
                                   placeholder="Where exactly is the problem?")
            
            onset = st.selectbox("📈 Onset", 
                               ["", "Sudden", "Gradual", "Constant", "Intermittent", "Worsening"], 
                               index=0)
        
        with col2:
            st.subheader("About You")
            age = st.number_input("🧍 Age", min_value=0, max_value=120, value=30)
            gender = st.selectbox("Gender", 
                                ["", "Male", "Female", "Other", "Prefer not to say"], 
                                index=0)
            
            medical_history = st.text_area("⚠️ Medical History", 
                                         placeholder="Any existing conditions?")
            
            current_meds = st.text_area("💊 Current Medications", 
                                     placeholder="List all medicines/supplements")
            
            allergies = st.text_input("🤧 Allergies", 
                                    placeholder="Medication/food allergies")
            
            lifestyle = st.text_area("🍏 Diet & Lifestyle", 
                                   placeholder="Diet preferences, restrictions, exercise etc.")
        
        submitted = st.form_submit_button("Get Recommendations")
    
    if submitted:
        if not symptoms.strip() and not st.session_state.response_data['uploaded_image']:
            st.error("Please describe symptoms or upload an image")
        else:
            with st.spinner("Analyzing your information..."):
                user_input = {
                    'symptoms': symptoms,
                    'duration': duration,
                    'severity': severity,
                    'location': location,
                    'onset': onset,
                    'age': age if age > 0 else "Not specified",
                    'gender': gender,
                    'medical_history': medical_history,
                    'medications': current_meds,
                    'allergies': allergies,
                    'lifestyle': lifestyle
                }
                
                image_analysis = None
                if st.session_state.response_data['uploaded_image']:
                    image_analysis = analyze_image(st.session_state.response_data['uploaded_image'])
                
                response = generate_response(user_input, language, image_analysis)
                st.session_state.response_data['text'] = response
                st.session_state.response_data['audio_generated'] = False
                st.session_state.response_data['show_results'] = True
                st.session_state.response_data['is_emergency'] = "Urgency Level: Emergency" in response
                st.session_state.response_data['nutrition_advice'] = None
                
                # Extract medication names for product search
                if "### Medication Recommendations:" in response:
                    medications = extract_medication_names(response)
                    st.session_state.response_data['medications_found'] = medications

    # Display results
    if st.session_state.response_data.get('show_results', False):
        colored_response = color_urgency_level(st.session_state.response_data['text'])
        enhanced_response = enhance_medication_display(colored_response)
        
        st.subheader("Health Assessment")
        
        if st.session_state.response_data.get('uploaded_image'):
            st.image(st.session_state.response_data['uploaded_image'], 
                    caption="Symptom Image Reference", 
                    width=300)
        
        st.markdown(enhanced_response, unsafe_allow_html=True)
        
        # Display medication purchase options if available
        if st.session_state.response_data.get('medications_found'):
            st.markdown("---")
            st.subheader("💊 Where to Buy Recommended Medications")
            
            for med in st.session_state.response_data['medications_found']:
                with st.expander(f"Purchase options for {med.capitalize()}"):
                    display_medication_products(med)
        
        # Medication safety tips
        st.info("""
        💊 Medication Safety Tips:
        - Always check for interactions
        - Start with lowest effective dose
        - Don't combine similar medications
        - Stop if side effects occur
        - Consult a doctor before taking new medications
        """)
        
        # Audio section
        st.markdown("---")
        st.subheader("🔊 Listen to Recommendations")
        if st.button("Generate Audio"):
            with st.spinner("Creating voice output..."):
                audio_path = text_to_speech(st.session_state.response_data['text'], language)
                st.session_state.response_data['audio_path'] = audio_path
                if audio_path:
                    autoplay_audio(audio_path)
        
        # Nutrition Recommendations Button
        st.markdown("---")
        if st.button("🍎 Get Nutrition Recommendations"):
            with st.spinner("Generating personalized nutrition advice..."):
                nutrition_prompt = f"""As a nutritionist, provide detailed dietary recommendations based on:
                
                Health Assessment: {st.session_state.response_data['text']}
                
                Patient Information:
                - Age: {age}
                - Gender: {gender}
                - Conditions: {medical_history}
                - Medications: {current_meds}
                - Allergies: {allergies}
                - Lifestyle: {lifestyle}
                
                Provide:
                1. Recommended foods and avoidances (consider allergies)
                2. Sample 1-day meal plan
                3. Key nutrients to focus on
                4. Hydration recommendations
                5. Supplement suggestions (if needed)
                6. Special considerations based on medications
                
                Format with clear headings and use food emojis for better readability."""
                
                nutrition_response = model.generate_content(nutrition_prompt)
                st.session_state.response_data['nutrition_advice'] = nutrition_response.text
        
        # Display nutrition advice if available
        if st.session_state.response_data.get('nutrition_advice'):
            st.markdown("---")
            st.subheader("🍏 Personalized Nutrition Plan")
            st.markdown(st.session_state.response_data['nutrition_advice'], unsafe_allow_html=True)
            
            # PDF Export
            if st.button("📄 Save as PDF"):
                pdf = FPDF()
                pdf.add_page()
                pdf.set_font("Arial", size=12)
                clean_text = re.sub(r'<[^>]*>', '', st.session_state.response_data['nutrition_advice'])
                pdf.multi_cell(0, 10, txt=clean_text)
                pdf.output("nutrition_plan.pdf")
                
                with open("nutrition_plan.pdf", "rb") as f:
                    st.download_button(
                        label="⬇️ Download Nutrition Plan",
                        data=f,
                        file_name="personalized_nutrition_plan.pdf",
                        mime="application/pdf"
                    )
        
        # Emergency services
        if st.session_state.response_data.get('is_emergency', False):
            st.markdown("---")
            st.subheader("🆘 Emergency Assistance")
            if gmaps:
                location_input = st.text_input("Enter your location for nearby help:")
                if location_input:
                    with st.spinner("Finding emergency services..."):
                        medical_data = get_nearby_medical_facilities(gmaps, location_input)
                        if medical_data:
                            show_medical_facilities_map(medical_data)
            st.markdown("""
            ### 📞 Emergency Contacts
            - **Local Emergency**: 102 or 112
            - **Poison Control**: 1800-425-1213
            - **Mental Health Crisis**: 14416 
            """)

if __name__ == "__main__":

    main()
