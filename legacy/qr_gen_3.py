import json
import pandas as pd
import qrcode
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import os

def get_text_dimensions(text, font):
    bbox = font.getbbox(text)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]

def wrap_text(text, font, max_width, tracking=0):
    words = text.split()
    lines = []
    current_line = words[0]
    
    for word in words[1:]:
        candidate = current_line + ' ' + word
        width, _ = get_text_dimensions(candidate, font)
        width += tracking * (len(candidate) - 1)  # letter-spacing counts toward the line
        if width <= max_width:
            current_line += ' ' + word
        else:
            lines.append(current_line)
            current_line = word
    
    lines.append(current_line)
    return lines

def create_caption_image(caption_text, qr_width, top_text=None):
    try:
        # Use absolute path for font files
        font_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'rob_batch.ttf')
        batch_font_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'rob_batch.ttf')
        try:
            caption_font = ImageFont.truetype(font_path, 60) # font size for caption
            batch_font = ImageFont.truetype(batch_font_path, 36) # font for the top row (name)
        except (OSError, IOError):
            print(f"Warning: Could not load custom font, using default font")
            caption_font = ImageFont.load_default() 
            batch_font = ImageFont.load_default()
        
        rendered_items = []  # List of tuples: (line_text, font, line_height, stroke, tracking)
        NAME_TRACKING = 5  # px of letter-spacing on the name row
        top_pad = 25 if top_text else 0  # breathing room between the QR and the name
        
        if top_text:
            batch_lines = wrap_text(top_text, batch_font, 580, tracking=NAME_TRACKING)
            b_bbox = batch_font.getbbox('hg')
            b_height = (b_bbox[3] - b_bbox[1]) + 20
            for line in batch_lines:
                rendered_items.append((line, batch_font, b_height, 1, NAME_TRACKING))  # stroke=1 -> faux bold
                
        caption_lines = wrap_text(caption_text, caption_font, 580)
        c_bbox = caption_font.getbbox('hg')
        c_height = (c_bbox[3] - c_bbox[1]) + 40
        for line in caption_lines:
            rendered_items.append((line, caption_font, c_height, 0, 0))
            
        caption_height = sum(item[2] for item in rendered_items) + top_pad
        
        caption_image = Image.new('RGB', (600, caption_height), color='white')
        draw = ImageDraw.Draw(caption_image)
        
        y = top_pad
        for line, font, h, stroke, tracking in rendered_items:
            if tracking:
                text_width = (sum(draw.textlength(c, font=font) for c in line)
                              + tracking * (len(line) - 1))
                x = (600 - text_width) / 2
                for ch in line:  # draw per character to apply letter-spacing
                    draw.text((x, y), ch, font=font, fill='black',
                              stroke_width=stroke, stroke_fill='black')
                    x += draw.textlength(ch, font=font) + tracking
            else:
                bbox = font.getbbox(line)
                x = (600 - (bbox[2] - bbox[0])) // 2
                draw.text((x, y), line, font=font, fill='black',
                          stroke_width=stroke, stroke_fill='black')
            y += h
            
        return caption_image
    except Exception as e:
        raise e

def generate_qr_code(link, caption):
    try:
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        
        qr.add_data(link)
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="black", back_color="white")
        qr_img = qr_img.resize((600, 600))
        
        qr_img_with_caption = Image.new('RGB', (qr_img.width, qr_img.height + caption.height),color='white')
        # default value 20 curr:(-10)
        qr_img_with_caption.paste(qr_img, (0, -10))
        # daflaut value -18 ---> curr(80)
        qr_img_with_caption.paste(caption, ((qr_img.width - caption.width) // 2, qr_img.height - 80))
        qr_img_with_caption = qr_img_with_caption.crop((0, 40, 600, qr_img.height - 80 + caption.height + 10))

        # pad (never scale) to a perfect square so the QR is not resampled
        side = max(qr_img_with_caption.size)
        square = Image.new('RGB', (side, side), color='white')
        square.paste(qr_img_with_caption,
                     ((side - qr_img_with_caption.width) // 2,
                      (side - qr_img_with_caption.height) // 2))
        qr_img_with_caption = square
        
        img_byte_array = BytesIO()
        # qr_img_with_caption.save(img_byte_array, format='PNG')
        qr_img_with_caption.save(img_byte_array, format='JPEG')
        return img_byte_array.getvalue()
        
    except Exception as e:
        raise e

def main():
    try:
        # Get input file path from user
        input_file = "Brigade.csv"  # Changed to relative path
        output_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.path.splitext(input_file)[0])
        
        # Create output directory if it doesn't exist
        os.makedirs(output_folder, exist_ok=True)
        
        try:
            # Check file extension to determine how to read the file
            file_extension = os.path.splitext(input_file)[1].lower()
            
            if file_extension == '.json':
                # Read JSON file
                with open(input_file, 'r') as f:
                    data = json.load(f)
                df = pd.DataFrame(data)
            elif file_extension == '.csv':
                # Read CSV file
                df = pd.read_csv(input_file)
            else:
                print(f"Unsupported file format: {file_extension}")
                print("Supported formats: .csv, .json")
                return
                
        except Exception as e:
            print(f"Error reading input file: {input_file}")
            print(f"Error: {str(e)}")
            return

        # required_columns = ['id', 'code']
        required_columns = ['qr_code']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            print(f"Missing required columns: {', '.join(missing_columns)}")
            return

        generated_files = []
        errors = []
        
        for index, row in df.iterrows():
            try:
                # qr code AZ  Customization
                # link = "https://mates.extraa.in/qr/AZ" + str(row['qr_id'])
                # caption_text = "AZ" + str(row['qr_id'])
                # filename = "AZ" + str(row['qr_id']) + ".png"
                # caption = create_caption_image(caption_text, 600)

                  # link = str(row['code'])
                # caption_text = str(row['code'])
                # filename = f"{str(row['id'])}.png"

                # qr code AA  Coustomization
                #link = "https://mates.extraa.in/qr/AA" + str(row['qr_id'])
                #caption_text = "AA" + str(row['qr_id'])
                #filename = "AA" + str(row['qr_id']) + ".png"
                #caption = create_caption_image(caption_text, 600)
                
                # qr code AZ  Coustomization
                # link = "https://mates.extraa.in/qr/" + str(row['qr_code'])
                # caption_text = str(row['qr_code'])
                # filename = str(row['qr_code']) + ".png"
                # caption = create_caption_image(caption_text, 600)
                
                # zomato qr code
                # link = str(row['qr_value'])
                # caption_text = str(row['name'])
                # filename = str(row['name']) + ".jpg"
                # caption = create_caption_image(caption_text, 400)

                # sangeetha code
                # link = "https://qr.extraa.in/qr/" + str(row['qr_code'])
                # caption_text = "TEST-"+str(row["name"])
                # filename = str(row["name"]) + ".png"
                # caption = create_caption_image(caption_text, 600)

                # #Cincin Customization
                # link = "https://cincineria.extraa.in/" + str(row['qr_code'])
                # caption_text =str(row['qr_code'])
                # filename = str(row['qr_code']) + ".png"
                # caption = create_caption_image(caption_text, 600)

                # #Extraa Cards Customization
                link = "https://www.extraacards.com/cards/"+ str(row['qr_code'])
                caption_text = str(row['qr_code'])          # row 2
                name_text = str(row['name']) if 'name' in row else None   # row 1
                filename = str(row['qr_code']) + ".png"    
                caption = create_caption_image(caption_text, 600, top_text=name_text)

                 # #Extraa POS Machine Qrs
                # link = str(row['qr_code'])
                # caption_text =str(row['name'])
                # filename = str(row['name']) + ".png"    
                # caption = create_caption_image(caption_text, 600)

                # Event Ticket
                # link = str(row['qr_id'])
                # caption_text ="VIP-"+str(row['qr_id'])
                # # clean_qr_id = str(row['qr_id']).replace("/", "_")
                # filename = str(row['qr_id']).strip()
                # if filename.endswith(" 1/1"):
                #         filename = filename[:-4] 
                # filename += ".png"
                # caption = create_caption_image(caption_text, 600)      

                # GOGAS LPG CARDS
                # link = '#' + str(row['qr_code'])
                # caption_text = '#' + str(row['qr_code'])
                # filename = 'qr_' + str(row['id']) + ".png"
                # caption = create_caption_image(caption_text, 600)

                #GOGAS CNG CARDS
                # link = str(row['qr_code'])
                # caption_text =  "FC"+"_"+str(row['qr_code'])
                # filename = "FC"+"_"+str(row['qr_code']) + ".png"
                # caption = create_caption_image(caption_text, 600)
                
                # client 
                # link = "https://event.collectiveculture.in/festival-2026"
                # caption_text = "Collective Culture"
                # filename = "Collective Culture" + str(row['qr_code']) + ".png"
                # caption = create_caption_image(caption_text, 600)

                qr_image_bytes = generate_qr_code(link, caption)                
                output_path = os.path.join(output_folder, filename)
                
                # Save the image locally
                with open(output_path, 'wb') as f:
                    f.write(qr_image_bytes)
                #
                generated_files.append({
                    'filename': filename,
                    'status': 'success',
                    'path': output_path
                })
                print(f"Generated file: {filename}")

                # break out if testing
                # break
                
            except Exception as e:
                errors.append({
                    'index': index,
                    'error': str(e)
                })
        
        print("\nQR code generation complete")
        print(f"Input file: {input_file}")
        print(f"Output folder: {output_folder}")
        print(f"Files generated: {len(generated_files)}")
        
        if errors:
            print("\nErrors encountered:")
            for error in errors:
                print(f"Row {error['index']}: {error['error']}")
        
    except Exception as e:
        print(f"Error in execution: {str(e)}")

if __name__ == "__main__":
    main()
#     cd /Users/aravind/Extraa/scriptcodes/qr_gen
#  source .venv/bin/activate
#  python3 qr_gen_2.py