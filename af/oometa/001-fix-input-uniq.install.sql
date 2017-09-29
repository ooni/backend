BEGIN;

select _v.register_patch( '001-fix-input-uniq', ARRAY[ '000-init' ], NULL );

-- `delete...` takes ages if online constraint check is performed
alter table measurement drop constraint measurement_input_no_fkey;

create temporary table inputdup as select * from (select min(input_no) as target, unnest(array_agg(input_no)) as dup from input group by input having count(*) > 1) as T1 where target != dup;

update measurement set input_no = target from inputdup where input_no = dup;

delete from input where input_no in (select dup from inputdup);

-- bring dropped constraint back
alter table only measurement add constraint measurement_input_no_fkey foreign key (input_no) references input(input_no);

alter table only input add constraint input_input_key unique (input);

COMMIT;

-- vacuum has to be done after commit
vacuum full input;
vacuum full measurement;
