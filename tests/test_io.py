import io
from zipfile import ZipFile

from ranch_ai.utils.io import load_pastures, load_uploaded_pastures


def test_example_pastures_load():
    pastures = load_pastures()
    assert len(pastures) == 1
    assert {
        "pasture_id",
        "name",
        "acres",
        "geometry",
        "centroid_lon",
        "centroid_lat",
        "boundary_status",
        "source_address",
    }.issubset(pastures.columns)
    assert pastures.loc[0, "name"] == "Caja Caliente Main Pasture"
    assert pastures.loc[0, "source_address"] == "711 N Scotty Road, Alpine, TX 79830"
    assert all(isinstance(polygon, list) for polygon in pastures["geometry"])


def test_kml_upload_loads_single_pasture():
    kml_text = """<?xml version="1.0" encoding="UTF-8"?>
    <kml xmlns="http://www.opengis.net/kml/2.2">
      <Document>
        <Placemark>
          <name>Caja Caliente Main Pasture</name>
          <ExtendedData>
            <Data name="pasture_id"><value>CC-001</value></Data>
          </ExtendedData>
          <Polygon>
            <outerBoundaryIs>
              <LinearRing>
                <coordinates>
                  -103.508361,29.606667,0 -103.511167,29.606639,0 -103.511139,29.606000,0 -103.508333,29.606028,0 -103.508361,29.606667,0
                </coordinates>
              </LinearRing>
            </outerBoundaryIs>
          </Polygon>
        </Placemark>
      </Document>
    </kml>
    """

    pastures = load_uploaded_pastures("caja_caliente.kml", kml_text.encode("utf-8"))

    assert len(pastures) == 1
    assert pastures.loc[0, "pasture_id"] == "CC-001"
    assert pastures.loc[0, "name"] == "Caja Caliente Main Pasture"
    assert pastures.loc[0, "acres"] > 0


def test_kmz_upload_loads_single_pasture():
    kml_text = """<?xml version="1.0" encoding="UTF-8"?>
    <kml xmlns="http://www.opengis.net/kml/2.2">
      <Document>
        <Placemark>
          <name>North Pasture</name>
          <Polygon>
            <outerBoundaryIs>
              <LinearRing>
                <coordinates>
                  -103.50,29.60,0 -103.51,29.60,0 -103.51,29.59,0 -103.50,29.59,0 -103.50,29.60,0
                </coordinates>
              </LinearRing>
            </outerBoundaryIs>
          </Polygon>
        </Placemark>
      </Document>
    </kml>
    """
    buffer = io.BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("doc.kml", kml_text)

    pastures = load_uploaded_pastures("north_pasture.kmz", buffer.getvalue())

    assert len(pastures) == 1
    assert pastures.loc[0, "name"] == "North Pasture"
    assert pastures.loc[0, "acres"] > 0
