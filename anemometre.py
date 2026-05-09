# =================================================================
# 🌬️ PILOTE DE L'ANÉMOMÈTRE (MESURE DE LA VITESSE DU VENT)
# =================================================================
from machine import ADC
import time
import math

class CapteurVent:
    """
    Cette classe calcule la vitesse du vent en mesurant le temps 
    écoulé entre deux détections magnétiques (effet Hall ou Reed).
    """
    
    def __init__(self, pin_adc=26, rayon_m=0.17, nb_aimants=2, coeff_k=2.8):
        # Initialisation de la lecture analogique sur la broche choisie
        self.capteur = ADC(pin_adc)
        
        # Paramètres physiques de l'appareil
        self.rayon = rayon_m        # Rayon des bras de l'anémomètre (en mètres)
        self.nb_aimants = nb_aimants # Nombre d'aimants fixés sur l'axe
        self.coeff_k = coeff_k      # Facteur de correction (frottements/aérodynamisme)
        
        # État du capteur (pour éviter de compter plusieurs fois le même aimant)
        self.aimant_present = False
        
        # Variables de chronométrage
        self.dernier_temps_aimant = 0  # Timestamp du dernier passage (ms)
        self.intervalle_ms = 0         # Durée écoulée entre deux passages (ms)
        self.vitesse_exacte = 0.0      # Résultat final en km/h

    def ecouter(self):
        """
        Méthode à appeler en boucle (très souvent). 
        Elle surveille le passage des aimants "en temps réel".
        """
        valeur = self.capteur.read_u16() # Lecture brute (0 à 65535)
        
        # DÉTECTION : Si la tension chute ou monte brutalement (présence d'aimant)
        # On vérifie aussi 'not self.aimant_present' pour ne valider qu'une seule impulsion
        if (valeur < 20000 or valeur > 42500) and not self.aimant_present:
            maintenant = time.ticks_ms() # On prend l'heure précise
            
            # Calcul du temps écoulé depuis le passage précédent
            if self.dernier_temps_aimant > 0:
                self.intervalle_ms = time.ticks_diff(maintenant, self.dernier_temps_aimant)
                
            self.dernier_temps_aimant = maintenant
            self.aimant_present = True # On marque l'aimant comme "déjà vu"
            
        # RÉINITIALISATION : Quand la valeur revient au neutre, l'aimant est parti
        elif (28000 < valeur < 38000) and self.aimant_present:
            self.aimant_present = False

    def lire_vitesse(self):
        """
        Calcule la vitesse finale en km/h basée sur le dernier intervalle mesuré.
        Inclut une sécurité pour le vent nul.
        """
        maintenant = time.ticks_ms()
        
        # SÉCURITÉ : Si aucun aimant n'est passé depuis plus de 2 secondes,
        # cela signifie que l'anémomètre s'est arrêté.
        if time.ticks_diff(maintenant, self.dernier_temps_aimant) > 2000:
            self.vitesse_exacte = 0.0
            self.intervalle_ms = 0
            
        # CALCUL MATHÉMATIQUE
        elif self.intervalle_ms > 0:
            # 1. Conversion de l'intervalle en secondes
            dt_secondes = self.intervalle_ms / 1000.0
            
            # 2. Temps nécessaire pour une rotation complète (360°)
            temps_un_tour = dt_secondes * self.nb_aimants
            
            # 3. Calcul de la fréquence de rotation (tours par seconde)
            frequence_hz = 1.0 / temps_un_tour
            
            # 4. Formule de la vitesse linéaire : V = 2 * pi * R * f
            # Résultat en mètres par seconde (m/s)
            vitesse_m_s = 2 * math.pi * self.rayon * frequence_hz
            
            # 5. Conversion en km/h (x 3.6) et application du coefficient de correction (k)
            self.vitesse_exacte = vitesse_m_s * 3.6 * self.coeff_k
            
        return self.vitesse_exacte, True