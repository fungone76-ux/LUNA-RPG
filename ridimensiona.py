from PIL import Image


def converti_in_pixel_art(input_path, output_path, target_size=64):
    # 1. Apri l'immagine grande generata dall'IA (es. 512x512)
    img = Image.open(input_path)

    # 2. Rimpicciolisci usando NEAREST (mantiene i bordi netti, non sfoca!)
    img_small = img.resize((target_size, target_size), resample=Image.NEAREST)

    # 3. Salva l'immagine piccola
    img_small.save(output_path)
    print(f"Immagine convertita a {target_size}x{target_size} pixel!")

# Esempio d'uso
# converti_in_pixel_art("guerriero_sd_512.png", "guerriero_pixel_64.png")