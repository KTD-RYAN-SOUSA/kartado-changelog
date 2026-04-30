# Migration 1: Only normalize keywords data (no indexes)

import gc
import os
import threading
import time
import uuid as uuid_maker
from concurrent.futures import ThreadPoolExecutor, as_completed

from django.db import migrations, transaction

from helpers.apps.record_filter import create_keywords


class MockOccurrenceType:
    def __init__(self, data):
        self.name = data.get("name", "")
        self.form_fields = data.get("form_fields", {})


class MockReporting:
    def __init__(self, data):
        self.number = data.get("number")
        self.road_name = data.get("road_name")
        self.km = data.get("km")
        self.road = None
        if data.get("road_name"):
            self.road = type("MockRoad", (), {"name": data.get("road_name")})()


def update_keywords_optimized_for_large_dataset(apps, schema_editor):
    """
    Highly optimized keywords update for large datasets (5M+ records).
    This runs BEFORE creating indexes for maximum efficiency.

    Set KEYWORDS_MIGRATION_THREADED=true environment variable to enable threading.
    """
    use_threading = os.getenv("KEYWORDS_MIGRATION_THREADED", "false").lower() == "true"
    db_alias = schema_editor.connection.alias
    Company = apps.get_model("companies", "Company")
    companies = Company.objects.using(db_alias).all().only("pk")

    if use_threading:
        print("🧵 Threading enabled - using multi-threaded keyword processing")
        for company in companies:
            print(f"🚀 Running process for company {str(company.pk)}")
            update_keywords_threaded(apps, db_alias, company)
    else:
        for company in companies:
            print(f"🚀 Running process for company {str(company.pk)}")
            update_keywords_sequential(apps, db_alias, company)


def update_keywords_sequential(apps, db_alias, company):
    """Original sequential implementation"""
    Reporting = apps.get_model("reportings", "Reporting")

    # Configuration for large datasets
    batch_size = 500  # Smaller batches for better memory management
    transaction_batch_size = 5000  # Commit every N records
    total = Reporting.objects.using(db_alias).filter(company_id=company.pk).count()

    print(f"\n🚀 Starting optimized keywords normalization for {total:,} records...")
    print(
        f"📊 Configuration: batch_size={batch_size}, transaction_batch_size={transaction_batch_size}"
    )
    print(
        "ℹ️  Note: Indexes will be created in the NEXT migration for optimal performance"
    )

    start_time = time.perf_counter()
    processed = 0
    reps_appended = 0
    updates_pending = []

    # Use iterator to avoid loading all records into memory
    queryset = (
        Reporting.objects.using(db_alias)
        .filter(company_id=company.pk)
        .only(
            "uuid",
            "company_id",
            "keywords",
            "form_data",
            "number",
            "road_name",
            "km",
            "occurrence_type",
            "road",
        )
        .prefetch_related("occurrence_type", "road")
        .iterator(chunk_size=batch_size)
    )

    for reporting in queryset:
        try:
            if reporting.occurrence_type:
                # Generate normalized keywords
                new_keywords = create_keywords(
                    reporting.form_data, reporting.occurrence_type, reporting
                )

                # Only update if keywords actually changed
                if new_keywords != reporting.keywords:
                    reporting.keywords = new_keywords
                    updates_pending.append(reporting)
                    reps_appended += 1

            processed += 1

            # Bulk update when batch is full
            if reps_appended >= batch_size:
                if updates_pending:
                    Reporting.objects.bulk_update(updates_pending, ["keywords"])
                    updates_pending.clear()
                    reps_appended = 0

                # Progress reporting
                elapsed = time.perf_counter() - start_time
                rate = processed / elapsed if elapsed > 0 else 0
                eta = (total - processed) / rate if rate > 0 else 0

                print(
                    f"📈 Progress: {processed:,}/{total:,} ({processed/total*100:.1f}%) - "
                    f"Rate: {rate:.1f} records/sec - ETA: {eta/60:.1f} min"
                )

                # Commit transaction periodically to avoid long locks
                if processed % transaction_batch_size == 0:
                    transaction.commit()
                    # Force garbage collection to free memory
                    gc.collect()

        except Exception as e:
            print(f"⚠️  Error processing record {reporting.uuid}: {e}")
            continue

    # Process remaining updates
    if updates_pending:
        Reporting.objects.bulk_update(updates_pending, ["keywords"])
        print(f"✅ Final batch: {len(updates_pending)} records updated")

    # Final statistics
    elapsed = time.perf_counter() - start_time
    rate = processed / elapsed if elapsed > 0 else 0
    print("\n🎉 Keywords normalization completed!")
    print("📊 Statistics:")
    print(f"   • Total processed: {processed:,} records")
    print(f"   • Total time: {elapsed/60:.1f} minutes")
    print(f"   • Average rate: {rate:.1f} records/sec")
    print("\n⏭️  Next: Run migration 0065 to create optimized indexes")


def reverse_keywords_update(apps, schema_editor):
    """Reverse migration - not implemented for safety"""
    print(
        "⚠️  Reverse migration not implemented - keywords normalization cannot be easily reversed."
    )
    print("   If needed, regenerate keywords using: python manage.py update_keywords")


def update_keywords_threaded(apps, db_alias, company):
    """
    Multi-threaded keywords update using ThreadPoolExecutor.
    Separates CPU-bound work (keyword generation) from I/O (database operations).
    """

    Reporting = apps.get_model("reportings", "Reporting")

    def process_keywords_batch(batch_records):
        """Process a batch of records in a worker thread"""

        results = []
        for record_data in batch_records:
            try:
                (
                    uuid,
                    form_data,
                    occurrence_type_data,
                    reporting_data,
                    current_keywords,
                ) = record_data

                if occurrence_type_data:
                    # Create mock objects for create_keywords

                    mock_occurrence_type = MockOccurrenceType(occurrence_type_data)
                    mock_reporting = MockReporting(reporting_data)

                    new_keywords = create_keywords(
                        form_data, mock_occurrence_type, mock_reporting
                    )

                    if new_keywords != current_keywords:
                        results.append((uuid, new_keywords))

            except Exception as e:
                print(f"⚠️  Thread error processing {uuid}: {e}")
                continue

        return results

    # Configuration
    batch_size = 300  # Smaller batches for threading
    num_workers = min(6, max(2, threading.active_count()))
    write_batch_size = 1000
    transaction_batch_size = 5000
    total = Reporting.objects.using(db_alias).filter(company_id=company.pk).count()

    print(f"🧵 Starting THREADED normalization for {total:,} records...")
    print(
        f"📊 Config: batch={batch_size}, workers={num_workers}, write_batch={write_batch_size}"
    )

    start_time = time.perf_counter()
    processed = 0
    reps_appended = 0
    pending_writes = []

    with ThreadPoolExecutor(
        max_workers=num_workers, thread_name_prefix="KeywordWorker"
    ) as executor:
        futures = []
        current_batch = []

        queryset = (
            Reporting.objects.using(db_alias)
            .filter(company_id=company.pk)
            .only(
                "uuid",
                "company_id",
                "keywords",
                "form_data",
                "number",
                "road_name",
                "km",
                "occurrence_type",
                "road",
            )
            .prefetch_related("occurrence_type", "road")
            .iterator(chunk_size=batch_size)
        )

        for reporting in queryset:
            try:
                # Serialize data for thread safety
                occurrence_type_data = None
                if reporting.occurrence_type:
                    occurrence_type_data = {
                        "name": reporting.occurrence_type.name,
                        "form_fields": reporting.occurrence_type.form_fields,
                    }

                reporting_data = {
                    "number": reporting.number,
                    "road_name": reporting.road_name
                    or (reporting.road.name if reporting.road else None),
                    "km": reporting.km,
                }

                current_batch.append(
                    (
                        str(reporting.uuid),
                        reporting.form_data,
                        occurrence_type_data,
                        reporting_data,
                        reporting.keywords,
                    )
                )

                processed += 1
                reps_appended += 1

                # Submit batch to workers
                if reps_appended >= batch_size:
                    future = executor.submit(
                        process_keywords_batch, current_batch.copy()
                    )
                    futures.append(future)
                    current_batch.clear()
                    reps_appended = 0

                    # Collect completed results
                    completed_futures = [f for f in futures if f.done()]
                    for future in completed_futures:
                        try:
                            batch_results = future.result()
                            pending_writes.extend(batch_results)
                        except Exception as e:
                            print(f"⚠️  Future error: {e}")

                    # Remove completed futures
                    futures = [f for f in futures if not f.done()]

                    # Write when batch is full
                    if len(pending_writes) >= write_batch_size:
                        if pending_writes:
                            # Prepare objects for bulk_update
                            updates_to_apply = []
                            updates_dict = {
                                uuid: keywords for uuid, keywords in pending_writes
                            }

                            # Fetch objects that need updating
                            objects_to_update = (
                                Reporting.objects.using(db_alias)
                                .filter(uuid__in=updates_dict.keys())
                                .in_bulk(field_name="uuid")
                            )

                            # Set new keywords on fetched objects
                            for uuid_str, keywords in updates_dict.items():
                                try:
                                    valid_uuid = uuid_maker.UUID(uuid_str)
                                except Exception as e:
                                    print(f"⚠️ UUID transformation error: {e}")
                                    valid_uuid = None
                                    continue
                                obj = objects_to_update.get(valid_uuid)
                                if obj:
                                    obj = objects_to_update[valid_uuid]
                                    obj.keywords = keywords
                                    updates_to_apply.append(obj)

                            # Bulk update
                            if updates_to_apply:
                                Reporting.objects.bulk_update(
                                    updates_to_apply, ["keywords"]
                                )

                            pending_writes.clear()

                        # Progress and cleanup
                        if processed % transaction_batch_size == 0:
                            transaction.commit()
                            gc.collect()

                        elapsed = time.perf_counter() - start_time
                        rate = processed / elapsed if elapsed > 0 else 0
                        eta = (total - processed) / rate if rate > 0 else 0
                        active_futures = len([f for f in futures if not f.done()])

                        print(
                            f"📈 Progress: {processed:,}/{total:,} ({processed/total*100:.1f}%) - "
                            f"Rate: {rate:.1f} rec/sec - ETA: {eta/60:.1f} min - "
                            f"Active: {active_futures} futures"
                        )

            except Exception as e:
                print(f"⚠️ Error preparing {reporting.uuid}: {e}")
                continue

        # Submit final batch
        if current_batch:
            future = executor.submit(process_keywords_batch, current_batch)
            futures.append(future)

        # Wait for all futures to complete
        print("🔄 Waiting for worker threads to finish...")
        for future in as_completed(futures):
            try:
                batch_results = future.result()
                pending_writes.extend(batch_results)
            except Exception as e:
                print(f"⚠️ Future completion error: {e}")

    # Final writes
    if pending_writes:
        updates_to_apply = []
        updates_dict = {uuid: keywords for uuid, keywords in pending_writes}

        # Fetch objects that need updating
        objects_to_update = (
            Reporting.objects.using(db_alias)
            .filter(uuid__in=updates_dict.keys())
            .in_bulk(field_name="uuid")
        )

        # Set new keywords on fetched objects
        for uuid_str, keywords in updates_dict.items():
            try:
                valid_uuid = uuid_maker.UUID(uuid_str)
            except Exception as e:
                print(f"⚠️ UUID transformation error: {e}")
                valid_uuid = None
                continue
            obj = objects_to_update.get(valid_uuid)
            if obj:
                obj.keywords = keywords
                updates_to_apply.append(obj)

        # Bulk update
        if updates_to_apply:
            Reporting.objects.bulk_update(updates_to_apply, ["keywords"])

        print(f"✅ Final threaded batch: {len(pending_writes)} records updated")

    elapsed = time.perf_counter() - start_time
    rate = processed / elapsed if elapsed > 0 else 0
    print("\n🎉 Threaded normalization completed!")
    print("📊 Statistics:")
    print(f"   • Total processed: {processed:,} records")
    print(f"   • Total time: {elapsed/60:.1f} minutes")
    print(f"   • Average rate: {rate:.1f} records/sec")
    print(f"   • Workers used: {num_workers}")


class Migration(migrations.Migration):

    dependencies = [
        ("reportings", "0064_merge_0063_auto_20250804_1317_0063_reportingbulkedit"),
    ]

    operations = [
        # Only normalize keywords data - NO INDEX CREATION
        migrations.RunPython(
            update_keywords_optimized_for_large_dataset,
            reverse_keywords_update,
        ),
    ]
