"""Shared pytest fixtures."""

import pytest

from ew.db import connect, create_schema


@pytest.fixture
def db():
    """In-memory SQLite database with schema created."""
    conn = connect(":memory:")
    create_schema(conn)
    return conn


@pytest.fixture
def cnf_dir(tmp_path):
    """Minimal CNF CSV fixture directory."""
    d = tmp_path / "cnf"
    d.mkdir()

    (d / "FOOD GROUP.csv").write_text(
        "FoodGroupID,FoodGroupCode,FoodGroupName,FoodGroupNameF\n"
        "1,1,Dairy and Egg Products,Produits laitiers\n"
        "2,2,Fruits,Fruits\n",
        encoding="latin-1",
    )
    (d / "NUTRIENT NAME.csv").write_text(
        "NutrientID,NutrientCode,NutrientSymbol,NutrientUnit,NutrientName,NutrientNameF,Tagname,NutrientDecimals\n"
        "203,203,PROT,g,PROTEIN,PROTEINES,PROCNT,2\n"
        "208,208,KCAL,kCal,ENERGY (KILOCALORIES),ENERGIE,ENERC_KCAL,0\n",
        encoding="latin-1",
    )
    (d / "FOOD NAME.csv").write_text(
        "FoodID,FoodCode,FoodGroupID,FoodSourceID,FoodDescription,FoodDescriptionF,"
        "FoodDateOfEntry,FoodDateOfPublication,CountryCode,ScientificName\n"
        "1,1,1,20,Whole milk,Lait entier,1981-01-01,,,Bos taurus\n"
        "2,2,2,20,Apple raw,Pomme crue,1981-01-01,,,Malus domestica\n",
        encoding="latin-1",
    )
    (d / "NUTRIENT AMOUNT.csv").write_text(
        "FoodID,NutrientID,NutrientValue,StandardError,NumberofObservations,NutrientSourceID,NutrientDateOfEntry\n"
        "1,203,3.2,0.1,5,102,2010-01-01\n"
        "1,208,61,0,5,102,2010-01-01\n"
        "2,203,0.3,0,3,102,2010-01-01\n",
        encoding="latin-1",
    )
    (d / "MEASURE NAME.csv").write_text(
        "MeasureID,MeasureDescription,MeasureDescriptionF,,\n"
        "341,1 cup,1 tasse,,\n"
        "383,1 tbsp,1 c. a soupe,,\n",
        encoding="latin-1",
    )
    (d / "CONVERSION FACTOR.csv").write_text(
        "FoodID,MeasureID,ConversionFactorValue,ConvFactorDateOfEntry\n"
        "1,341,2.44,1997-01-01\n"
        "1,383,0.153,1997-01-01\n"
        "2,341,1.25,1997-01-01\n",
        encoding="latin-1",
    )
    return d


@pytest.fixture
def usda_dir(tmp_path):
    """Minimal USDA CSV fixture directory."""
    d = tmp_path / "usda"
    d.mkdir()

    (d / "food_category.csv").write_text(
        "id,description\n"
        "1,Dairy and Egg Products\n"
        "9,Fruits and Fruit Juices\n"
    )
    (d / "nutrient.csv").write_text(
        "id,name,unit_name,nutrient_nbr,rank\n"
        "1003,Protein,G,203,600.0\n"
        "1008,Energy,KCAL,208,300.0\n"
        "1004,Total lipid (fat),G,204,800.0\n"
    )
    (d / "food.csv").write_text(
        '"fdc_id","data_type","description","food_category_id","publication_date"\n'
        '"167512","sr_legacy_food","Milk, whole","1","2019-04-01"\n'
        '"09003","sr_legacy_food","Apples, raw","9","2019-04-01"\n'
    )
    (d / "food_nutrient.csv").write_text(
        "id,fdc_id,nutrient_id,amount,data_points,derivation_id,min,max,median,footnote,min_year_acqured\n"
        "1,167512,1003,3.2,5,1,,,,,""\n"
        "2,167512,1008,61,5,1,,,,,""\n"
        "3,09003,1003,0.3,3,1,,,,,""\n"
    )
    (d / "food_portion.csv").write_text(
        "id,fdc_id,seq_num,amount,measure_unit_id,portion_description,modifier,gram_weight,data_points,footnote,min_year_acquired\n"
        "1,167512,1,1.0,1000,cup,,244.0,5,,\n"
        "2,167512,2,1.0,1001,tbsp,,15.3,5,,\n"
    )
    (d / "measure_unit.csv").write_text(
        "id,name,abbreviation\n"
        "1000,cup,cup\n"
        "1001,tablespoon,tbsp\n"
    )
    return d
