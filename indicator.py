# --- PARÁMETROS ---
# Puedes definir aquí los parámetros de tu indicador. Por ejemplo:
# WINDOW = 14

# --- ESCRIBE TU CÓDIGO ---
class MyIndicator:
    def calculate(self, df):
        # Aquí es donde implementarás la lógica de tu indicador.
        # 'df' es un DataFrame de pandas con los datos históricos del activo (OHLCV).
        # Debe retornar un diccionario con al menos dos claves:
        # 'data': Una lista de diccionarios, donde cada diccionario contiene 'time' y 'value'.
        #         'time' debe ser una marca de tiempo (timestamp) o una cadena de fecha/hora.
        #         'value' es el valor del indicador para ese punto en el tiempo.
        # 'metadata': Un diccionario con cualquier información adicional que desees retornar sobre el indicador.

        # Ejemplo básico: Retornar el precio de cierre como un indicador
        indicator_data = []
        for index, row in df.iterrows():
            indicator_data.append({
                "time": row["time"], # Asegúrate de que tu DataFrame tenga una columna 'time'
                "value": row["close"]
            })

        metadata = {
            "name": "My Basic Close Price Indicator",
            "description": "Just returns the closing price."
        }

        return {
            "data": indicator_data,
            "metadata": metadata
        }